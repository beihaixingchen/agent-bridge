"""Configuration loading: TOML file + environment variable overrides."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class NodeConfig(BaseModel):
    id: str = "node"
    name: str = "Agent Bridge Node"
    description: str = ""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class PolicyConfig(BaseModel):
    default: str = "deny"
    grants_file: str = "grants.json"


class MeshConfig(BaseModel):
    enabled: bool = False
    token: str = ""
    self_url: str = ""
    seeds: list[str] = Field(default_factory=list)
    announce_interval: int = 300


class TailscaleConfig(BaseModel):
    enabled: bool = False
    mode: str = "serve"


class Config(BaseModel):
    node: NodeConfig = NodeConfig()
    server: ServerConfig = ServerConfig()
    policy: PolicyConfig = PolicyConfig()
    mesh: MeshConfig = MeshConfig()
    tailscale: TailscaleConfig = TailscaleConfig()
    data_dir: str = ".agent-bridge"

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def keys_file(self) -> Path:
        return self.data_path / "keys.json"

    @property
    def grants_file(self) -> Path:
        return self.data_path / "grants.json"

    @property
    def peers_file(self) -> Path:
        return self.data_path / "peers.json"

    @property
    def base_url(self) -> str:
        return f"http://{self.server.host}:{self.server.port}"


def _find_config_file(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
    for candidate in [Path("config.toml"), Path.home() / ".agent-bridge" / "config.toml"]:
        if candidate.exists():
            return candidate
    return None


def load_config(config_path: str | None = None) -> Config:
    """Load config from a TOML file, then apply environment variable overrides."""
    data: dict = {}

    cfg_file = _find_config_file(config_path)
    if cfg_file:
        with open(cfg_file, "rb") as f:
            data = tomllib.load(f)

    # --- environment variable overrides ---
    if v := os.environ.get("AGENT_BRIDGE_NODE_ID"):
        data.setdefault("node", {})["id"] = v
    if v := os.environ.get("AGENT_BRIDGE_HOST"):
        data.setdefault("server", {})["host"] = v
    if v := os.environ.get("AGENT_BRIDGE_PORT"):
        data.setdefault("server", {})["port"] = int(v)
    if v := os.environ.get("AGENT_BRIDGE_DATA_DIR"):
        data["data_dir"] = v
    if v := os.environ.get("MESH_TOKEN"):
        data.setdefault("mesh", {})["token"] = v
    if v := os.environ.get("AGENT_BRIDGE_MESH_SELF_URL"):
        data.setdefault("mesh", {})["self_url"] = v
    if v := os.environ.get("AGENT_BRIDGE_MESH_ENABLED"):
        data.setdefault("mesh", {})["enabled"] = v.lower() in ("true", "1", "yes")

    config = Config(**data)

    # Expand ${VAR} references in string fields (e.g. mesh.token = "${MESH_TOKEN}")
    config.mesh.token = os.path.expandvars(config.mesh.token)

    return config
