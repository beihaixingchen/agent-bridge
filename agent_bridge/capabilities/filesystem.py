"""Filesystem capabilities: read_file, write_file, list_dir."""

from __future__ import annotations

from pathlib import Path

from agent_bridge.capabilities.base import Capability, CapabilityResult


class ReadFileCapability(Capability):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read a file from the local filesystem."

    async def invoke(self, args: dict) -> CapabilityResult:
        path = args.get("path")
        if not path:
            return CapabilityResult(success=False, error="missing 'path' argument")
        try:
            content = Path(path).resolve().read_text(encoding="utf-8")
            return CapabilityResult(success=True, data=content)
        except Exception as e:
            return CapabilityResult(success=False, error=str(e))


class WriteFileCapability(Capability):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file on the local filesystem."

    async def invoke(self, args: dict) -> CapabilityResult:
        path = args.get("path")
        content = args.get("content", "")
        if not path:
            return CapabilityResult(success=False, error="missing 'path' argument")
        try:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return CapabilityResult(
                success=True, data=f"wrote {len(content)} bytes to {path}"
            )
        except Exception as e:
            return CapabilityResult(success=False, error=str(e))


class ListDirCapability(Capability):
    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List directory contents."

    async def invoke(self, args: dict) -> CapabilityResult:
        path = args.get("path", ".")
        try:
            p = Path(path).resolve()
            entries = []
            for entry in sorted(p.iterdir()):
                kind = "d" if entry.is_dir() else "f"
                entries.append(f"{kind} {entry.name}")
            return CapabilityResult(success=True, data="\n".join(entries))
        except Exception as e:
            return CapabilityResult(success=False, error=str(e))
