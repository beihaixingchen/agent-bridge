"""MeshManager: peer discovery, announce loop, and peer table persistence."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from agent_bridge.mesh.client import PeerClient


class PeerInfo:
    def __init__(
        self,
        url: str,
        card: dict | None = None,
        last_seen: float = 0.0,
        healthy: bool = False,
    ) -> None:
        self.url = url
        self.card = card
        self.last_seen = last_seen
        self.healthy = healthy

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "card": self.card,
            "last_seen": self.last_seen,
            "healthy": self.healthy,
        }


class MeshManager:
    """Manages peer discovery and the periodic announce loop."""

    def __init__(
        self,
        node_id: str,
        base_url: str,
        token: str,
        seeds: list[str],
        announce_interval: int = 300,
        peers_file: Path | None = None,
    ) -> None:
        self.node_id = node_id
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.seeds = seeds
        self.announce_interval = announce_interval
        self.peers_file = peers_file
        self.peers: dict[str, PeerInfo] = {}
        self._task: asyncio.Task | None = None

        self._load_peers()

    def _load_peers(self) -> None:
        if self.peers_file and self.peers_file.exists():
            raw = json.loads(self.peers_file.read_text())
            for url, data in raw.items():
                self.peers[url] = PeerInfo(
                    url=url,
                    card=data.get("card"),
                    last_seen=data.get("last_seen", 0.0),
                    healthy=data.get("healthy", False),
                )

    def _save_peers(self) -> None:
        if self.peers_file:
            data = {url: p.to_dict() for url, p in self.peers.items()}
            self.peers_file.parent.mkdir(parents=True, exist_ok=True)
            self.peers_file.write_text(json.dumps(data, indent=2))

    def get_healthy_peers(self) -> list[PeerInfo]:
        return [p for p in self.peers.values() if p.healthy]

    def add_peer(self, url: str, card: dict | None = None) -> None:
        if url in self.peers:
            self.peers[url].last_seen = time.time()
            self.peers[url].healthy = True
            if card:
                self.peers[url].card = card
        else:
            self.peers[url] = PeerInfo(
                url=url, card=card, last_seen=time.time(), healthy=True
            )
        self._save_peers()

    def handle_announce(self, card: dict, peers: list[dict]) -> dict:
        """Handle an inbound announce from a peer; return our card + peers."""
        peer_url = card.get("url", "")
        if peer_url:
            self.add_peer(peer_url, card)

        for p in peers:
            url = p.get("url", "")
            if url and url not in self.peers and url != self.base_url:
                self.peers[url] = PeerInfo(
                    url=url, card=p.get("card"), last_seen=0.0, healthy=False
                )

        self._save_peers()
        return {
            "agent_card": {"url": self.base_url, "name": self.node_id},
            "peers": [p.to_dict() for p in self.peers.values()],
        }

    async def announce_loop(self, own_card: dict) -> None:
        """Periodically announce to all seeds and known peers."""
        while True:
            await self._announce_once(own_card)
            self._mark_stale()
            await asyncio.sleep(self.announce_interval)

    async def _announce_once(self, own_card: dict) -> None:
        targets = list(self.seeds) + [p.url for p in self.peers.values()]
        known_peers = [p.to_dict() for p in self.peers.values()]

        for url in targets:
            if url == self.base_url:
                continue
            try:
                client = PeerClient(url, self.token)
                resp = await client.announce(own_card, known_peers)
                peer_card = resp.get("agent_card", {})
                peer_url = peer_card.get("url", url)
                self.add_peer(peer_url, peer_card)

                for p in resp.get("peers", []):
                    purl = p.get("url", "")
                    if purl and purl != self.base_url and purl not in self.peers:
                        self.peers[purl] = PeerInfo(
                            url=purl,
                            card=p.get("card"),
                            last_seen=0.0,
                            healthy=False,
                        )
                self._save_peers()
            except Exception:
                pass  # peer unreachable — will be marked stale by _mark_stale

    def _mark_stale(self) -> None:
        threshold = self.announce_interval * 3
        now = time.time()
        for peer in self.peers.values():
            if peer.last_seen > 0 and now - peer.last_seen > threshold:
                peer.healthy = False
        self._save_peers()

    def start(self, own_card: dict) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.announce_loop(own_card))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
