"""Grant store: JSON-backed persistence for agent capability grants."""

from __future__ import annotations

import json
from pathlib import Path

from agent_bridge.policy.models import AgentGrant, CapabilityGrant


class GrantStore:
    """JSON-backed store for agent capability grants."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._grants: dict[str, AgentGrant] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            content = self.path.read_text().strip()
            if not content:
                return
            raw = json.loads(content)
            for agent_id, data in raw.items():
                self._grants[agent_id] = AgentGrant(**data)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {aid: g.model_dump() for aid, g in self._grants.items()}
        self.path.write_text(json.dumps(data, indent=2))

    def get(self, agent_id: str) -> AgentGrant | None:
        return self._grants.get(agent_id)

    def set_grant(self, agent_id: str, capability: str, grant: CapabilityGrant) -> None:
        if agent_id not in self._grants:
            self._grants[agent_id] = AgentGrant(agent_id=agent_id)
        self._grants[agent_id].capabilities[capability] = grant
        self._save()

    def remove_grant(self, agent_id: str, capability: str) -> None:
        if agent_id in self._grants:
            self._grants[agent_id].capabilities.pop(capability, None)
            self._save()

    def remove_agent(self, agent_id: str) -> None:
        self._grants.pop(agent_id, None)
        self._save()

    def list(self) -> list[AgentGrant]:
        return list(self._grants.values())
