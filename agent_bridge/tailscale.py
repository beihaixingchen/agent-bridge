"""Tailscale integration: hostname lookup, Serve (tailnet-only), Funnel (public)."""

from __future__ import annotations

import asyncio
import json
import shutil


async def get_hostname() -> str | None:
    """Get this machine's Tailscale hostname (e.g. ``mbp.tail1234.ts.net``)."""
    if not shutil.which("tailscale"):
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "tailscale", "status", "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        data = json.loads(stdout)
        return data.get("Self", {}).get("DNSName", "").rstrip(".")
    except Exception:
        return None


async def setup_serve(port: int) -> bool:
    """Configure Tailscale Serve (tailnet-only) for the given port."""
    if not shutil.which("tailscale"):
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "tailscale", "serve", "--bg", f"http://localhost:{port}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def setup_funnel(port: int) -> bool:
    """Configure Tailscale Funnel (public internet) for the given port."""
    if not shutil.which("tailscale"):
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "tailscale", "funnel", "--bg", f"http://localhost:{port}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False


async def teardown(port: int = 0) -> bool:
    """Remove Tailscale Serve/Funnel configuration."""
    if not shutil.which("tailscale"):
        return False
    try:
        args = ["tailscale", "serve", "--https=443", "off"]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return True
    except Exception:
        return False
