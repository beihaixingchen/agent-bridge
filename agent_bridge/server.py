"""Server assembly: A2A routes + admin API + auth middleware + mesh announce."""

from __future__ import annotations

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent_bridge.agent_card import build_agent_card
from agent_bridge.auth import AuthMiddleware, KeyStore
from agent_bridge.capabilities.filesystem import (
    ListDirCapability,
    ReadFileCapability,
    WriteFileCapability,
)
from agent_bridge.capabilities.registry import CapabilityRegistry
from agent_bridge.capabilities.shell import RunCommandCapability
from agent_bridge.config import Config, load_config
from agent_bridge.executor import BridgeAgentExecutor
from agent_bridge.policy.enforcer import Enforcer
from agent_bridge.policy.models import CapabilityConstraint
from agent_bridge.policy.store import GrantStore


def create_default_registry() -> CapabilityRegistry:
    """Create a registry with all built-in capabilities."""
    registry = CapabilityRegistry()
    registry.register(ReadFileCapability())
    registry.register(WriteFileCapability())
    registry.register(ListDirCapability())
    registry.register(RunCommandCapability())
    return registry


def _parse_constraints(constraint_args: list[str]) -> CapabilityConstraint:
    """Parse --constraint key=value flags into a CapabilityConstraint."""
    constraints = CapabilityConstraint()
    for item in constraint_args:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        if key == "path_prefix":
            constraints.path_prefix = value
        elif key == "allowed_commands":
            constraints.allowed_commands = value.split(",")
        elif key == "max_output_bytes":
            constraints.max_output_bytes = int(value)
    return constraints


def create_admin_routes(
    key_store: KeyStore,
    grant_store: GrantStore,
    registry: CapabilityRegistry,
    config: Config,
) -> list[Route]:
    """Create admin API routes for managing keys, grants, and inspection."""

    async def health(_request: Request):
        return JSONResponse({"status": "ok", "node": config.node.id})

    async def list_capabilities(_request: Request):
        caps = [
            {"name": c.name, "description": c.description}
            for c in registry.list()
        ]
        return JSONResponse({"capabilities": caps})

    async def list_agents(_request: Request):
        return JSONResponse({"agents": key_store.list_agents()})

    async def list_grants(_request: Request):
        return JSONResponse(
            {"grants": [g.model_dump() for g in grant_store.list()]}
        )

    return [
        Route("/health", health, methods=["GET"]),
        Route("/admin/capabilities", list_capabilities, methods=["GET"]),
        Route("/admin/agents", list_agents, methods=["GET"]),
        Route("/admin/grants", list_grants, methods=["GET"]),
    ]


def create_mesh_routes(config: Config, mesh_manager=None) -> list[Route]:
    """Create mesh discovery routes (only if mesh is enabled)."""
    if not config.mesh.enabled:
        return []

    async def announce(request: Request):
        body = await request.json()
        card = body.get("agent_card", {})
        peers = body.get("peers", [])
        if mesh_manager:
            resp = mesh_manager.handle_announce(card, peers)
            return JSONResponse(resp)
        return JSONResponse(
            {"agent_card": {"url": config.base_url, "name": config.node.id}, "peers": []}
        )

    async def list_peers(_request: Request):
        if mesh_manager:
            return JSONResponse(
                {"peers": [p.to_dict() for p in mesh_manager.peers.values()]}
            )
        return JSONResponse({"peers": []})

    return [
        Route("/a2a/announce", announce, methods=["POST"]),
        Route("/a2a/peers", list_peers, methods=["GET"]),
    ]


def create_app(config: Config) -> Starlette:
    """Create the full Starlette app: A2A routes + admin + mesh + auth."""
    key_store = KeyStore(config.keys_file)
    grant_store = GrantStore(config.grants_file)
    registry = create_default_registry()
    enforcer = Enforcer(grant_store, default=config.policy.default)

    agent_card = build_agent_card(config, registry)

    request_handler = DefaultRequestHandler(
        agent_executor=BridgeAgentExecutor(registry, enforcer),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )

    # Assemble all routes
    routes = []
    routes.extend(create_agent_card_routes(agent_card))
    routes.extend(create_jsonrpc_routes(request_handler, "/"))
    routes.extend(create_admin_routes(key_store, grant_store, registry, config))
    routes.extend(create_mesh_routes(config))

    app = Starlette(
        routes=routes,
        middleware=[
            Middleware(
                AuthMiddleware,
                key_store=key_store,
                mesh_token=config.mesh.token,
            )
        ],
    )

    # Attach state for CLI access
    app.state.key_store = key_store
    app.state.grant_store = grant_store
    app.state.registry = registry
    app.state.config = config

    return app


def serve(
    config_path: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Start the agent-bridge server."""
    config = load_config(config_path)
    if host:
        config.server.host = host
    if port:
        config.server.port = port

    app = create_app(config)

    caps = ", ".join(c.name for c in app.state.registry.list())
    print(f"agent-bridge starting on {config.server.host}:{config.server.port}")
    print(f"  Node ID:       {config.node.id}")
    print(f"  Agent Card:    {config.base_url}/.well-known/agent-card.json")
    print(f"  Capabilities:  {caps}")
    print(f"  Mesh enabled:  {config.mesh.enabled}")
    print(f"  Data dir:      {config.data_path}")

    uvicorn.run(app, host=config.server.host, port=config.server.port)
