"""Policy enforcer: checks inbound capability calls against grant policies."""

from __future__ import annotations

from dataclasses import dataclass

from agent_bridge.policy.store import GrantStore


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""


class Enforcer:
    """Checks whether an agent may invoke a capability with given args."""

    def __init__(self, store: GrantStore, default: str = "deny") -> None:
        self.store = store
        self.default = default

    def check(self, agent_id: str | None, capability: str, args: dict) -> PolicyDecision:
        # Local callers (no auth, e.g. CLI) bypass policy
        if agent_id is None or agent_id == "local":
            return PolicyDecision(allowed=True, reason="local caller")

        # "mesh-peer" is the identity used by peer announce.
        # Actual capability calls from peers must carry an agent API key,
        # so a "mesh-peer" identity should not get capabilities.
        if agent_id == "mesh-peer":
            return PolicyDecision(
                allowed=False, reason="mesh token cannot invoke capabilities"
            )

        agent_grant = self.store.get(agent_id)
        if agent_grant is None:
            return PolicyDecision(
                allowed=False, reason=f"no grants for agent '{agent_id}'"
            )

        cap_grant = agent_grant.get(capability)
        if cap_grant is None:
            return PolicyDecision(
                allowed=False,
                reason=f"capability '{capability}' not granted to '{agent_id}'",
            )

        if not cap_grant.allowed:
            return PolicyDecision(
                allowed=False,
                reason=f"capability '{capability}' explicitly denied for '{agent_id}'",
            )

        # Constraint checks
        c = cap_grant.constraints

        if "path" in args and args["path"] is not None:
            if not c.check_path(args["path"]):
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        f"path '{args['path']}' outside allowed prefix "
                        f"'{c.path_prefix}'"
                    ),
                )

        if "command" in args and args["command"] is not None:
            if not c.check_command(args["command"]):
                return PolicyDecision(
                    allowed=False,
                    reason=f"command not in allowlist {c.allowed_commands}",
                )

        return PolicyDecision(allowed=True)
