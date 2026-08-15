"""PeerClient: A2A JSON-RPC client for calling remote agent-bridge peers."""

from __future__ import annotations

import json

import httpx


class PeerClient:
    """Minimal A2A client: discover, announce, and invoke capabilities on a peer."""

    def __init__(self, base_url: str, token: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    async def get_agent_card(self) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/.well-known/agent-card.json",
            )
            resp.raise_for_status()
            return resp.json()

    async def announce(self, card: dict, peers: list[dict]) -> dict:
        """Announce this node to a peer; receive the peer's card + peer list."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/a2a/announce",
                json={"agent_card": card, "peers": peers},
                headers={"Authorization": f"Bearer {self.token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def send_message(self, op: str, args: dict, context_id: str | None = None) -> dict:
        """Send a capability request to a remote peer via A2A message/send."""
        message_body = json.dumps({"op": op, "args": args})

        params: dict = {
            "message": {
                "messageId": f"ab-{id(args)}",
                "role": "ROLE_USER",
                "parts": [{"text": message_body}],
            }
        }
        if context_id:
            params["context_id"] = context_id

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": params,
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "A2A-Version": "1.0",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def invoke_capability(self, op: str, args: dict) -> dict:
        """Send a message and extract the JSON result from the artifact."""
        response = await self.send_message(op, args)

        # A2A v1.0 wraps artifacts under result.task.artifacts
        result = response.get("result", {})
        task = result.get("task", result)
        for artifact in task.get("artifacts", []):
            for part in artifact.get("parts", []):
                if "text" in part:
                    try:
                        return json.loads(part["text"])
                    except (json.JSONDecodeError, KeyError):
                        return {
                            "success": False,
                            "error": "malformed response",
                            "raw": part.get("text", ""),
                        }
        return {"success": False, "error": "no artifact in response", "raw": response}
