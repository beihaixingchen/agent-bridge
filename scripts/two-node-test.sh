#!/usr/bin/env bash
# Local two-node simulation: starts two agent-bridge instances on different
# ports, lets them discover each other via mesh announce, then invokes a
# capability from node-a to node-b.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

rm -rf /tmp/ab-node-a /tmp/ab-node-b
PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT

MESH_TOKEN="abm_test_token_shared"

mkdir -p /tmp/ab-node-a /tmp/ab-node-b

cat > /tmp/ab-node-a/config.toml << EOF
data_dir = "/tmp/ab-node-a"

[node]
id = "node-a"
name = "Node A (MacBook)"
description = "Simulated node A"

[server]
host = "127.0.0.1"
port = 9801

[mesh]
enabled = true
token = "$MESH_TOKEN"
self_url = "http://127.0.0.1:9801"
seeds = ["http://127.0.0.1:9802"]
announce_interval = 2
EOF

cat > /tmp/ab-node-b/config.toml << EOF
data_dir = "/tmp/ab-node-b"

[node]
id = "node-b"
name = "Node B (GPU Server)"
description = "Simulated node B"

[server]
host = "127.0.0.1"
port = 9802

[mesh]
enabled = true
token = "$MESH_TOKEN"
self_url = "http://127.0.0.1:9802"
seeds = ["http://127.0.0.1:9801"]
announce_interval = 2
EOF

echo "=== Generating keys and grants ==="

# Node A: generate key for alice, grant capabilities
uv run agent-bridge --config /tmp/ab-node-a/config.toml key generate alice 2>&1 | tail -2
uv run agent-bridge --config /tmp/ab-node-a/config.toml grant add alice read_file --constraint path_prefix=/ 2>&1
uv run agent-bridge --config /tmp/ab-node-a/config.toml grant add alice run_command --constraint allowed_commands=echo,whoami,hostname 2>&1

# Node B: generate key for bob, grant capabilities
uv run agent-bridge --config /tmp/ab-node-b/config.toml key generate bob 2>&1 | tail -2
uv run agent-bridge --config /tmp/ab-node-b/config.toml grant add bob read_file --constraint path_prefix=/ 2>&1
uv run agent-bridge --config /tmp/ab-node-b/config.toml grant add bob run_command --constraint allowed_commands=echo,whoami,hostname 2>&1

# Register alice's key (from node-a) on node-b too, so node-a can call node-b as alice
python3 -c "
import json
with open('/tmp/ab-node-a/keys.json') as f:
    keys_a = json.load(f)
with open('/tmp/ab-node-b/keys.json') as f:
    keys_b = json.load(f)
keys_b['alice'] = keys_a['alice']
with open('/tmp/ab-node-b/keys.json', 'w') as f:
    json.dump(keys_b, f, indent=2)
"
uv run agent-bridge --config /tmp/ab-node-b/config.toml grant add alice read_file --constraint path_prefix=/ 2>&1
uv run agent-bridge --config /tmp/ab-node-b/config.toml grant add alice run_command --constraint allowed_commands=echo,whoami,hostname 2>&1

ALICE_KEY=$(python3 -c "import json; print(json.load(open('/tmp/ab-node-a/keys.json'))['alice'])")

echo ""
echo "=== Starting Node A (port 9801) ==="
uv run agent-bridge --config /tmp/ab-node-a/config.toml serve &
PIDS+=($!)
sleep 2

echo "=== Starting Node B (port 9802) ==="
uv run agent-bridge --config /tmp/ab-node-b/config.toml serve &
PIDS+=($!)
sleep 2

echo ""
echo "=== Waiting for mesh discovery (announce_interval=2s) ==="
sleep 5

echo ""
echo "=== Node A peers ==="
curl -s http://127.0.0.1:9801/a2a/peers -H "Authorization: Bearer $MESH_TOKEN" | python3 -m json.tool 2>&1 | head -20

echo ""
echo "=== Node B peers ==="
curl -s http://127.0.0.1:9802/a2a/peers -H "Authorization: Bearer $MESH_TOKEN" | python3 -m json.tool 2>&1 | head -20

echo ""
echo "=== Cross-node: node-a calls node-b read_file /etc/hostname ==="
uv run agent-bridge --config /tmp/ab-node-a/config.toml peer invoke \
  http://127.0.0.1:9802 read_file --arg path=/etc/hostname --token "$ALICE_KEY" 2>&1

echo ""
echo "=== Cross-node: node-a calls node-b run_command hostname ==="
uv run agent-bridge --config /tmp/ab-node-a/config.toml peer invoke \
  http://127.0.0.1:9802 run_command --arg command=hostname --token "$ALICE_KEY" 2>&1

echo ""
echo "=== Cross-node: node-a calls node-b run_command rm (denied) ==="
uv run agent-bridge --config /tmp/ab-node-a/config.toml peer invoke \
  http://127.0.0.1:9802 run_command --arg command="rm -rf /tmp/x" --token "$ALICE_KEY" 2>&1

echo ""
echo "=== Test complete ==="
