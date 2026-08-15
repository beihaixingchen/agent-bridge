"""MCP server: exposes agent-bridge remote capabilities as MCP tools.

This lets AI agents (Claude Code, OpenCode, etc.) invoke capabilities on
remote machines through the standard MCP protocol, without manually running
`agent-bridge peer invoke`.

Tools exposed:
  - peer_list:        list discovered peer machines
  - peer_read_file:    read a file on a remote machine
  - peer_run_command:  execute a shell command on a remote machine
  - peer_list_dir:     list directory on a remote machine
  - peer_write_file:   write a file on a remote machine
"""

from __future__ import annotations

import json

from mcp.server.mcpserver.server import MCPServer

from agent_bridge.config import Config, load_config
from agent_bridge.mesh.client import PeerClient


def _load_json(path) -> dict:
    """Load JSON from a path, returning empty dict if missing or empty."""
    if path.exists():
        content = path.read_text().strip()
        if content:
            return json.loads(content)
    return {}


def _get_peer_token(config: Config, peer_url: str) -> str:
    """Look up the API key for a peer URL from peer_keys.json."""
    peer_keys = _load_json(config.data_path / "peer_keys.json")
    return peer_keys.get(peer_url, "")


def create_mcp_server(config: Config) -> MCPServer:
    """Create an MCP server that exposes remote agent-bridge capabilities."""
    mcp = MCPServer(
        name="agent-bridge",
        version="0.1.0",
        description="Access remote machines via agent-bridge mesh network",
    )

    @mcp.tool()
    def peer_list() -> str:
        """List all discovered peer machines in the mesh network.

        Returns a table of peers with their URLs, names, and health status.
        Use this first to find available remote machines, then call
        peer_read_file or peer_run_command with the peer_url.
        """
        peers_data = _load_json(config.peers_file)
        if not peers_data:
            return (
                "No peers discovered yet. Make sure agent-bridge serve is "
                "running and mesh is enabled."
            )
        lines = []
        for url, info in peers_data.items():
            healthy = "healthy" if info.get("healthy") else "stale"
            card = info.get("card") or {}
            name = card.get("name", "?")
            lines.append(f"{name:20s} {url:50s} [{healthy}]")
        return "\n".join(lines)

    @mcp.tool()
    async def peer_read_file(peer_url: str, path: str) -> str:
        """Read a file on a remote machine.

        Args:
            peer_url: URL of the remote machine (from peer_list)
            path: File path on the remote machine (e.g. /etc/os-release or C:/Users/...)

        Returns the file contents as text.
        """
        token = _get_peer_token(config, peer_url)
        if not token:
            return (
                f"No API key configured for peer {peer_url}.\n"
                f"Run: agent-bridge peer key add {peer_url} <api-key>"
            )
        client = PeerClient(peer_url, token)
        result = await client.invoke_capability("read_file", {"path": path})
        if result.get("success"):
            return result.get("data", "")
        return f"Error: {result.get('error', 'unknown')}"

    @mcp.tool()
    async def peer_run_command(peer_url: str, command: str, timeout: int = 30) -> str:
        """Execute a shell command on a remote machine and return the output.

        Args:
            peer_url: URL of the remote machine (from peer_list)
            command: Shell command to execute
            timeout: Max execution time in seconds (default 30)

        Returns stdout (and stderr if any).
        """
        token = _get_peer_token(config, peer_url)
        if not token:
            return f"No API key configured for peer {peer_url}."
        client = PeerClient(peer_url, token)
        result = await client.invoke_capability(
            "run_command", {"command": command, "timeout": timeout}
        )
        if result.get("success"):
            return result.get("data", "")
        return f"Error: {result.get('error', 'unknown')}"

    @mcp.tool()
    async def peer_list_dir(peer_url: str, path: str = ".") -> str:
        """List directory contents on a remote machine.

        Args:
            peer_url: URL of the remote machine (from peer_list)
            path: Directory path to list (default: current directory)

        Returns a listing of files and directories.
        """
        token = _get_peer_token(config, peer_url)
        if not token:
            return f"No API key configured for peer {peer_url}."
        client = PeerClient(peer_url, token)
        result = await client.invoke_capability("list_dir", {"path": path})
        if result.get("success"):
            return result.get("data", "")
        return f"Error: {result.get('error', 'unknown')}"

    @mcp.tool()
    async def peer_write_file(peer_url: str, path: str, content: str) -> str:
        """Write content to a file on a remote machine.

        Args:
            peer_url: URL of the remote machine (from peer_list)
            path: File path on the remote machine
            content: Text content to write

        Returns confirmation of the write.
        """
        token = _get_peer_token(config, peer_url)
        if not token:
            return f"No API key configured for peer {peer_url}."
        client = PeerClient(peer_url, token)
        result = await client.invoke_capability(
            "write_file", {"path": path, "content": content}
        )
        if result.get("success"):
            return result.get("data", "OK")
        return f"Error: {result.get('error', 'unknown')}"

    return mcp


def run_mcp(config_path: str | None = None) -> None:
    """Start the MCP server (stdio transport)."""
    config = load_config(config_path)
    mcp = create_mcp_server(config)
    mcp.run()
