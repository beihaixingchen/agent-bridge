# Two-Machine Deployment Guide

This guide walks you through connecting two real machines with agent-bridge via Tailscale.

## Prerequisites

1. **Two machines** (e.g. your MacBook + a GPU server), both with internet access
2. **Python 3.11+** on both machines
3. **uv** installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
4. **Tailscale** installed on both machines (https://tailscale.com/download)

## Step 1: Install Tailscale

On **both** machines:

```bash
# macOS
brew install tailscale
# or download the app from https://tailscale.com/download/mac

# Linux
curl -fsSL https://tailscale.com/install.sh | sh

# Log in (both machines must use the same Tailscale account)
tailscale up
```

Verify both machines can see each other:

```bash
tailscale status
# You should see both machines listed
```

## Step 2: Clone and install agent-bridge

On **both** machines:

```bash
git clone https://github.com/beihaixingchen/agent-bridge.git
cd agent-bridge
uv sync
```

## Step 3: Generate a shared mesh token

On **one** machine:

```bash
uv run agent-bridge mesh-token
# Output: MESH_TOKEN=abm_xxxxxxxxxxxxxxxx
```

Copy this token — both machines must use the identical value.

## Step 4: Create config files

### Machine A (e.g. MacBook)

```bash
cat > ~/.agent-bridge/config.toml << 'EOF'
data_dir = "~/.agent-bridge"

[node]
id = "macbook"
name = "MacBook Pro"
description = "Development machine"

[server]
host = "127.0.0.1"
port = 8765

[mesh]
enabled = true
token = "abm_YOUR_SHARED_TOKEN_HERE"
# Leave self_url empty — Tailscale auto-setup will detect it
self_url = ""
seeds = ["https://gpu-server.tailXXXX.ts.net"]
announce_interval = 30

[tailscale]
enabled = true
mode = "serve"
EOF
```

### Machine B (e.g. GPU server)

```bash
cat > ~/.agent-bridge/config.toml << 'EOF'
data_dir = "~/.agent-bridge"

[node]
id = "gpu-server"
name = "GPU Server"
description = "Training and inference server"

[server]
host = "127.0.0.1"
port = 8765

[mesh]
enabled = true
token = "abm_YOUR_SHARED_TOKEN_HERE"
self_url = ""
seeds = ["https://macbook.tailYYYY.ts.net"]
announce_interval = 30

[tailscale]
enabled = true
mode = "serve"
EOF
```

> **Tip:** Use `tailscale status` to find each machine's hostname (`*.ts.net`).
> Replace the `seeds` URL with the other machine's Tailscale hostname.

## Step 5: Generate API keys and grants

On **Machine A** (for an agent on Machine B to call it):

```bash
uv run agent-bridge key generate bob
# Save the output key

uv run agent-bridge grant add bob read_file --constraint path_prefix=/data/
uv run agent-bridge grant add bob run_command --constraint allowed_commands=nvidia-smi,python3,pip
```

On **Machine B** (for an agent on Machine A to call it):

```bash
uv run agent-bridge key generate alice
uv run agent-bridge grant add alice read_file --constraint path_prefix=/
uv run agent-bridge grant add alice run_command --constraint allowed_commands=nvidia-smi,ls,cat
```

## Step 6: Start the servers

On **both** machines:

```bash
uv run agent-bridge serve
```

You should see:

```
agent-bridge starting on 127.0.0.1:8765
  Node ID:       macbook
  Tailscale:     serve → https://macbook.tailYYYY.ts.net
  Mesh:          macbook @ https://macbook.tailYYYY.ts.net
  Seeds:         https://gpu-server.tailXXXX.ts.net
```

## Step 7: Verify mesh discovery

On either machine:

```bash
# Get the mesh token from config
MESH_TOKEN=$(grep token ~/.agent-bridge/config.toml | awk -F'"' '{print $2}')

# List discovered peers (uses mesh token for auth)
curl -s https://macbook.tailYYYY.ts.net/a2a/peers \
  -H "Authorization: Bearer $MESH_TOKEN" | python3 -m json.tool
```

You should see the other machine listed as a healthy peer.

## Step 8: Invoke a remote capability

From Machine A, call Machine B:

```bash
# Get alice's API key (registered on Machine B)
ALICE_KEY="abk_xxx..."  # from Step 5

uv run agent-bridge peer invoke \
  https://gpu-server.tailXXXX.ts.net \
  run_command \
  --arg command=nvidia-smi \
  --token "$ALICE_KEY"
```

Or read a file on the remote machine:

```bash
uv run agent-bridge peer invoke \
  https://gpu-server.tailXXXX.ts.net \
  read_file \
  --arg path=/etc/os-release \
  --token "$ALICE_KEY"
```

## Architecture

```
Machine A (MacBook)                 Machine B (GPU Server)
┌──────────────────────┐           ┌──────────────────────┐
│  agent-bridge        │           │  agent-bridge        │
│  :8765 (localhost)   │           │  :8765 (localhost)   │
│       ↕              │           │       ↕              │
│  Tailscale Serve     │←────────→│  Tailscale Serve     │
│  https://mb.ts.net   │  A2A +   │  https://gpu.ts.net  │
│                      │  announce│                      │
└──────────────────────┘           └──────────────────────┘
```

- **Tailscale Serve** proxies HTTPS (port 443) to localhost:8765
- Traffic stays within your tailnet (not exposed to public internet)
- **Mesh token** authenticates peer-to-peer announce
- **Per-agent API keys** authenticate capability calls
- **Policy enforcer** blocks unauthorized operations on each machine

## Tips

- **Tailscale Funnel** (public): change `mode = "funnel"` if you need the endpoint reachable from the public internet (e.g. helping a remote user who isn't on your tailnet). Use with caution.
- **Firewall**: Tailscale Serve only exposes port 443 via Tailscale's proxy. Your local port 8765 stays bound to localhost — no firewall changes needed.
- **Multiple agents**: register multiple API keys (one per agent/person). Each gets independent grants.
- **Revoke access**: `agent-bridge key revoke <agent_id>` instantly removes access.
