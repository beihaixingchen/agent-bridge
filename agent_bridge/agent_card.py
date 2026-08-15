"""Build an A2A AgentCard from config and registered capabilities."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from agent_bridge.capabilities.registry import CapabilityRegistry
from agent_bridge.config import Config


def build_agent_card(config: Config, registry: CapabilityRegistry) -> AgentCard:
    """Build an A2A AgentCard advertising this node's capabilities as skills."""
    base_url = config.base_url

    skills = [
        AgentSkill(
            id=cap.name,
            name=cap.name,
            description=cap.description,
            input_modes=["application/json"],
            output_modes=["application/json"],
            tags=["agent-bridge"],
        )
        for cap in registry.list()
    ]

    return AgentCard(
        name=config.node.name,
        description=config.node.description or f"agent-bridge node: {config.node.id}",
        version="0.1.0",
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=base_url,
                protocol_version="1.0",
            )
        ],
        skills=skills,
    )
