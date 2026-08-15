"""CLI entry point: agent-bridge.

Commands:
  serve              Start the A2A server
  key generate       Generate an API key for a remote agent
  key revoke         Revoke an agent's key
  key list           List registered agents
  grant add          Grant a capability to an agent (with optional constraints)
  grant remove        Remove a capability grant
  grant list          List all grants
  capabilities       List available capabilities
  mesh-token         Generate a shared mesh token
  peer list          List discovered peers
  peer invoke        Invoke a capability on a remote peer
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets

from agent_bridge.auth import KeyStore
from agent_bridge.config import load_config
from agent_bridge.policy.models import CapabilityGrant
from agent_bridge.policy.store import GrantStore
from agent_bridge.server import _parse_constraints, create_default_registry


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------
def cmd_serve(args: argparse.Namespace) -> None:
    from agent_bridge.server import serve

    serve(config_path=args.config, host=args.host, port=args.port)


# ---------------------------------------------------------------------------
# key management
# ---------------------------------------------------------------------------
def cmd_key_generate(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    key_store = KeyStore(config.keys_file)
    key = key_store.generate(args.agent_id)
    print(f"Agent:   {args.agent_id}")
    print(f"API Key: {key}")
    print(f"Store:   {config.keys_file}")


def cmd_key_revoke(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    key_store = KeyStore(config.keys_file)
    key_store.revoke(args.agent_id)
    print(f"Revoked key for agent: {args.agent_id}")


def cmd_key_list(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    key_store = KeyStore(config.keys_file)
    agents = key_store.list_agents()
    if not agents:
        print("No agents registered.")
        return
    for agent_id, masked in agents.items():
        print(f"  {agent_id}: {masked}")


# ---------------------------------------------------------------------------
# grant management
# ---------------------------------------------------------------------------
def cmd_grant_add(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    grant_store = GrantStore(config.grants_file)
    constraints = _parse_constraints(args.constraint)
    grant = CapabilityGrant(allowed=True, constraints=constraints)
    grant_store.set_grant(args.agent_id, args.capability, grant)
    print(f"Granted '{args.capability}' to '{args.agent_id}'")
    for c in args.constraint:
        print(f"  constraint: {c}")


def cmd_grant_remove(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    grant_store = GrantStore(config.grants_file)
    grant_store.remove_grant(args.agent_id, args.capability)
    print(f"Removed grant: '{args.capability}' from '{args.agent_id}'")


def cmd_grant_list(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    grant_store = GrantStore(config.grants_file)
    grants = grant_store.list()
    if not grants:
        print("No grants configured.")
        return
    for g in grants:
        print(f"Agent: {g.agent_id}")
        for cap, grant in g.capabilities.items():
            cons = grant.constraints
            details = []
            if cons.path_prefix:
                details.append(f"path_prefix={cons.path_prefix}")
            if cons.allowed_commands:
                details.append(f"commands={cons.allowed_commands}")
            if cons.max_output_bytes:
                details.append(f"max_bytes={cons.max_output_bytes}")
            detail_str = ", ".join(details) if details else "no constraints"
            print(f"  {cap}: {'allowed' if grant.allowed else 'denied'} ({detail_str})")


# ---------------------------------------------------------------------------
# capabilities
# ---------------------------------------------------------------------------
def cmd_capabilities(args: argparse.Namespace) -> None:
    registry = create_default_registry()
    for cap in registry.list():
        print(f"  {cap.name:16s}  {cap.description}")


# ---------------------------------------------------------------------------
# mesh token
# ---------------------------------------------------------------------------
def cmd_mesh_token(args: argparse.Namespace) -> None:
    token = "abm_" + secrets.token_urlsafe(32)
    print(f"MESH_TOKEN={token}")
    print("Set this in .env on all nodes in the same mesh.")


# ---------------------------------------------------------------------------
# peer management
# ---------------------------------------------------------------------------
async def _peer_list(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if not config.peers_file.exists():
        print("No peers discovered.")
        return
    raw = json.loads(config.peers_file.read_text())
    if not raw:
        print("No peers discovered.")
        return
    for url, data in raw.items():
        healthy = "healthy" if data.get("healthy") else "stale"
        card = data.get("card") or {}
        name = card.get("name", "?")
        print(f"  {url}  [{healthy}]  name={name}")


def cmd_peer_list(args: argparse.Namespace) -> None:
    asyncio.run(_peer_list(args))


async def _peer_invoke(args: argparse.Namespace) -> None:
    from agent_bridge.mesh.client import PeerClient

    config = load_config(args.config)
    token = args.token or config.mesh.token

    cap_args: dict = {}
    for item in args.cap_args:
        if "=" in item:
            k, v = item.split("=", 1)
            cap_args[k] = v

    client = PeerClient(args.peer_url, token)
    try:
        card = await client.get_agent_card()
        print(f"Peer: {card.get('name', 'unknown')}")
    except Exception as e:
        print(f"Warning: could not fetch agent card: {e}")

    result = await client.invoke_capability(args.op, cap_args)
    print(json.dumps(result, indent=2))


def cmd_peer_invoke(args: argparse.Namespace) -> None:
    asyncio.run(_peer_invoke(args))


# ---------------------------------------------------------------------------
# argument parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-bridge",
        description="Multi-computer agent collaboration bridge",
    )
    parser.add_argument("--config", help="Path to config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    p = sub.add_parser("serve", help="Start the A2A server")
    p.add_argument("--host", help="Override bind host")
    p.add_argument("--port", type=int, help="Override bind port")
    p.set_defaults(func=cmd_serve)

    # key
    p = sub.add_parser("key", help="Manage agent API keys")
    ks = p.add_subparsers(dest="key_command", required=True)

    p = ks.add_parser("generate", help="Generate an API key for an agent")
    p.add_argument("agent_id", help="Unique agent identifier (e.g. 'alice')")
    p.set_defaults(func=cmd_key_generate)

    p = ks.add_parser("revoke", help="Revoke an agent's API key")
    p.add_argument("agent_id")
    p.set_defaults(func=cmd_key_revoke)

    p = ks.add_parser("list", help="List registered agents")
    p.set_defaults(func=cmd_key_list)

    # grant
    p = sub.add_parser("grant", help="Manage capability grants")
    gs = p.add_subparsers(dest="grant_command", required=True)

    p = gs.add_parser("add", help="Grant a capability to an agent")
    p.add_argument("agent_id")
    p.add_argument("capability", help="Capability name (e.g. read_file)")
    p.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Constraint: key=value (e.g. path_prefix=/tmp)",
    )
    p.set_defaults(func=cmd_grant_add)

    p = gs.add_parser("remove", help="Remove a capability grant")
    p.add_argument("agent_id")
    p.add_argument("capability")
    p.set_defaults(func=cmd_grant_remove)

    p = gs.add_parser("list", help="List all grants")
    p.set_defaults(func=cmd_grant_list)

    # capabilities
    p = sub.add_parser("capabilities", help="List available capabilities")
    p.set_defaults(func=cmd_capabilities)

    # mesh-token
    p = sub.add_parser("mesh-token", help="Generate a shared mesh token")
    p.set_defaults(func=cmd_mesh_token)

    # peer
    p = sub.add_parser("peer", help="Manage and query mesh peers")
    ps = p.add_subparsers(dest="peer_command", required=True)

    p = ps.add_parser("list", help="List discovered peers")
    p.set_defaults(func=cmd_peer_list)

    p = ps.add_parser("invoke", help="Invoke a capability on a remote peer")
    p.add_argument("peer_url", help="Peer base URL (e.g. http://node-b:8765)")
    p.add_argument("op", help="Capability name (e.g. read_file)")
    p.add_argument(
        "--arg",
        action="append",
        default=[],
        dest="cap_args",
        help="Argument: key=value (e.g. path=/etc/hostname)",
    )
    p.add_argument("--token", help="API key for the remote peer")
    p.set_defaults(func=cmd_peer_invoke)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
