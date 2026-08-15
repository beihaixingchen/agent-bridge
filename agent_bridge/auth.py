"""Authentication: per-agent API keys + mesh token, exposed via Starlette middleware."""

from __future__ import annotations

import contextvars
import json
import secrets
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# Holds the authenticated caller's agent_id for the duration of a request.
# The executor reads this to enforce policy.
current_caller: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_caller", default=None
)

# Paths that require no authentication (agent card discovery, health probes).
PUBLIC_PATHS = frozenset({
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
    "/health",
    "/live",
    "/ready",
})


class KeyStore:
    """Manages API keys for agents allowed to call this node."""

    def __init__(self, path: Path):
        self.path = path
        self._keys: dict[str, str] = {}  # agent_id -> key
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            content = self.path.read_text().strip()
            if content:
                self._keys = json.loads(content)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._keys, indent=2))

    def generate(self, agent_id: str) -> str:
        key = "abk_" + secrets.token_urlsafe(32)
        self._keys[agent_id] = key
        self._save()
        return key

    def revoke(self, agent_id: str) -> None:
        self._keys.pop(agent_id, None)
        self._save()

    def resolve(self, token: str) -> str | None:
        """Resolve a bearer token to an agent_id. Returns None if unknown."""
        for agent_id, key in self._keys.items():
            if secrets.compare_digest(key, token):
                return agent_id
        return None

    def list_agents(self) -> dict[str, str]:
        """Return agent_id -> masked key (for display)."""
        return {aid: k[:8] + "..." for aid, k in self._keys.items()}

    def has_agent(self, agent_id: str) -> bool:
        return agent_id in self._keys


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer-token authentication for all inbound requests.

    Accepts two token types:
    - Agent API keys (per-agent, managed via CLI)
    - Mesh token (shared across nodes, for peer announce)

    The resolved agent_id is stored in the ``current_caller`` contextvar so
    the executor can enforce per-capability policy.
    """

    def __init__(self, app, key_store: KeyStore, mesh_token: str = ""):
        super().__init__(app)
        self.key_store = key_store
        self.mesh_token = mesh_token

    async def dispatch(self, request: Request, call_next):
        current_caller.set(None)

        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/.well-known/"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

            # Try agent API keys first
            agent_id = self.key_store.resolve(token)
            if agent_id:
                current_caller.set(agent_id)
                return await call_next(request)

            # Try mesh token (for peer-to-peer announce)
            if self.mesh_token and secrets.compare_digest(token, self.mesh_token):
                current_caller.set("mesh-peer")
                return await call_next(request)

        return JSONResponse({"error": "unauthorized"}, status_code=401)
