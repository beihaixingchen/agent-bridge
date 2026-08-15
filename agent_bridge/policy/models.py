"""Policy models: grants and constraints for per-agent capability authorization."""

from __future__ import annotations

import shlex

from pydantic import BaseModel, Field


class CapabilityConstraint(BaseModel):
    """Constraints on how a capability may be used by a grantee.

    Supported constraint fields (all optional — None means unrestricted):
      - path_prefix:      for filesystem capabilities, the allowed path prefix
      - allowed_commands:  for shell capabilities, the command allowlist (first token)
      - max_output_bytes:  truncate output beyond this many bytes
    """

    path_prefix: str | None = None
    allowed_commands: list[str] | None = None
    max_output_bytes: int | None = None

    def check_path(self, path: str) -> bool:
        if self.path_prefix is None:
            return True
        return path.startswith(self.path_prefix)

    def check_command(self, command: str) -> bool:
        if self.allowed_commands is None:
            return True
        try:
            parts = shlex.split(command)
        except ValueError:
            return False
        return bool(parts) and parts[0] in self.allowed_commands


class CapabilityGrant(BaseModel):
    """A grant of a single capability to an agent."""

    allowed: bool = True
    constraints: CapabilityConstraint = Field(default_factory=CapabilityConstraint)


class AgentGrant(BaseModel):
    """All grants for one agent."""

    agent_id: str
    capabilities: dict[str, CapabilityGrant] = Field(default_factory=dict)

    def get(self, capability: str) -> CapabilityGrant | None:
        return self.capabilities.get(capability)
