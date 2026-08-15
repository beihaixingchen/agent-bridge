"""BridgeAgentExecutor: routes inbound A2A tasks to local capabilities.

Protocol
--------
A remote agent sends an A2A ``message/send`` whose text body is JSON:

    {"op": "read_file", "args": {"path": "/etc/hosts"}}

The executor:
  1. Parses the JSON request.
  2. Reads the caller identity from the ``current_caller`` contextvar
     (set by AuthMiddleware).
  3. Asks the Enforcer whether this caller may invoke this capability
     with these args.
  4. Invokes the capability (or returns a denial).
  5. Returns the result as a JSON text artifact.
"""

from __future__ import annotations

import json

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

from agent_bridge.auth import current_caller
from agent_bridge.capabilities.registry import CapabilityRegistry
from agent_bridge.policy.enforcer import Enforcer


class BridgeAgentExecutor(AgentExecutor):
    """Routes inbound A2A tasks to local capabilities with policy enforcement."""

    def __init__(self, registry: CapabilityRegistry, enforcer: Enforcer) -> None:
        self.registry = registry
        self.enforcer = enforcer

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Processing capability request..."),
        )

        query = get_message_text(context.message)

        # --- parse request ---
        try:
            request = json.loads(query)
            op = request.get("op", "")
            args = request.get("args", {})
        except (json.JSONDecodeError, AttributeError):
            # Non-JSON input: return help text
            caps = self.registry.names()
            await updater.add_artifact(
                parts=[
                    new_text_part(
                        text=(
                            "agent-bridge ready. "
                            f"Available capabilities: {', '.join(caps)}\n"
                            'Send JSON: {"op": "<capability>", "args": {...}}'
                        ),
                        media_type="text/plain",
                    )
                ]
            )
            await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)
            return

        # --- enforce policy ---
        caller = current_caller.get()
        decision = self.enforcer.check(caller, op, args)
        if not decision.allowed:
            await self._reply(updater, {"success": False, "error": f"denied: {decision.reason}"})
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message(f"Denied: {decision.reason}"),
            )
            return

        # --- invoke capability ---
        cap = self.registry.get(op)
        if cap is None:
            await self._reply(
                updater, {"success": False, "error": f"unknown capability: {op}"}
            )
            await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)
            return

        result = await cap.invoke(args)

        # --- optionally truncate output ---
        max_bytes = None
        if caller and (grant := self.enforcer.store.get(caller)):
            if cg := grant.get(op):
                max_bytes = cg.constraints.max_output_bytes
        data = result.data
        if max_bytes and len(data) > max_bytes:
            data = data[:max_bytes] + f"\n[truncated at {max_bytes} bytes]"

        await self._reply(
            updater,
            {
                "success": result.success,
                "data": data,
                "error": result.error,
            },
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Capability invoked."),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancel is not supported.")

    @staticmethod
    async def _reply(updater: TaskUpdater, payload: dict) -> None:
        await updater.add_artifact(
            parts=[
                new_text_part(
                    text=json.dumps(payload),
                    media_type="application/json",
                )
            ]
        )
