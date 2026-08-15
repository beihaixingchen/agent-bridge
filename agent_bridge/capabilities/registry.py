"""Capability registry: holds all capabilities available on this node."""

from __future__ import annotations

from agent_bridge.capabilities.base import Capability


class CapabilityRegistry:
    """Registry of capabilities available on this node."""

    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}

    def register(self, cap: Capability) -> None:
        self._caps[cap.name] = cap

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def list(self) -> list[Capability]:
        return list(self._caps.values())

    def names(self) -> list[str]:
        return list(self._caps.keys())
