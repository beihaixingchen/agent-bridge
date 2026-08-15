"""Mesh: peer discovery, A2A client for calling remote nodes."""

from __future__ import annotations

from agent_bridge.mesh.client import PeerClient
from agent_bridge.mesh.manager import MeshManager, PeerInfo

__all__ = ["PeerClient", "MeshManager", "PeerInfo"]
