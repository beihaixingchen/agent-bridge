# agent-bridge

Multi-computer agent collaboration bridge. Lets AI agents on different machines discover each other, talk via the A2A protocol, and securely invoke each other's capabilities — filesystem, shell, task delegation — with per-agent, per-capability authorization.

## Why

When two computers each run an AI agent (Claude Code, Codex, OpenCode, etc.), the human becomes a copy-paste relay between them. `agent-bridge` removes that bottleneck: agents talk to each other directly, but only within the boundaries you explicitly grant.

## Architecture

```
┌──────────────────────────────────────────────────┐
│  agent-bridge (runs on each machine)             │
│                                                  │
│  A2A Server ──── AgentCard + JSON-RPC endpoint   │
│      │                                           │
│      ├── Auth (per-agent API keys)               │
│      ├── Policy Enforcer (capability grants)     │
│      └── Capabilities                            │
│           ├── read_file / write_file / list_dir  │
│           └── run_command                        │
│                                                  │
│  Mesh Manager ──── peer discovery + announce     │
│  Tailscale ──── zero-config secure networking    │
└──────────────────────────────────────────────────┘
```

- **A2A** (Agent2Agent protocol) — how agents talk to each other
- **MCP** (Model Context Protocol) — how agents access tools (orthogonal, not bundled here)
- **Tailscale** — secure WireGuard mesh networking, handles NAT traversal
- **Capability grants** — the key differentiator: you decide exactly what a remote agent may do on your machine

## Quick start

```bash
# Install
uv sync

# Generate an API key for a remote agent
agent-bridge key generate alice

# Grant alice read access to /tmp
agent-bridge grant add alice read_file --constraint path_prefix=/tmp

# Start the server
agent-bridge serve
```

On the other machine, do the same, then point agents at each other's A2A endpoint.

## License

MIT
