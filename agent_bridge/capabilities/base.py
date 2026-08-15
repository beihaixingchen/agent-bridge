"""Capabilities: local machine operations exposed to remote agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class CapabilityResult(BaseModel):
    """Result of a capability invocation."""

    success: bool
    data: str = ""
    error: str = ""


class Capability(ABC):
    """A capability exposes a local machine operation to remote agents.

    Each capability is advertised as an A2A AgentSkill and can be invoked
    by an authenticated remote agent (subject to policy enforcement).
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    async def invoke(self, args: dict) -> CapabilityResult: ...
