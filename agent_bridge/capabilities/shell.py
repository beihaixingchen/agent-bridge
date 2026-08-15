"""Shell capability: run_command with timeout."""

from __future__ import annotations

import asyncio

from agent_bridge.capabilities.base import Capability, CapabilityResult


class RunCommandCapability(Capability):
    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return "Execute a shell command and return stdout/stderr."

    async def invoke(self, args: dict) -> CapabilityResult:
        command = args.get("command")
        cwd = args.get("cwd")
        timeout = args.get("timeout", 30)
        if not command:
            return CapabilityResult(success=False, error="missing 'command' argument")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            return CapabilityResult(
                success=proc.returncode == 0,
                data=output,
                error="" if proc.returncode == 0 else f"exit code {proc.returncode}",
            )
        except asyncio.TimeoutError:
            return CapabilityResult(
                success=False, error=f"command timed out after {timeout}s"
            )
        except Exception as e:
            return CapabilityResult(success=False, error=str(e))
