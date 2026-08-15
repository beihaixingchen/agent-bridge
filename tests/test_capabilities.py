"""Tests for filesystem and shell capabilities."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from agent_bridge.capabilities.filesystem import (
    ListDirCapability,
    ReadFileCapability,
    WriteFileCapability,
)
from agent_bridge.capabilities.shell import RunCommandCapability


@pytest.mark.asyncio
async def test_read_file_success() -> None:
    cap = ReadFileCapability()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello world")
        path = f.name
    result = await cap.invoke({"path": path})
    assert result.success
    assert "hello world" in result.data


@pytest.mark.asyncio
async def test_read_file_missing_path() -> None:
    cap = ReadFileCapability()
    result = await cap.invoke({})
    assert not result.success
    assert "path" in result.error


@pytest.mark.asyncio
async def test_read_file_nonexistent() -> None:
    cap = ReadFileCapability()
    result = await cap.invoke({"path": "/nonexistent/path/xyz"})
    assert not result.success


@pytest.mark.asyncio
async def test_write_file_success() -> None:
    cap = WriteFileCapability()
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "subdir" / "output.txt")
        result = await cap.invoke({"path": path, "content": "test content"})
        assert result.success
        assert Path(path).read_text() == "test content"


@pytest.mark.asyncio
async def test_write_file_missing_path() -> None:
    cap = WriteFileCapability()
    result = await cap.invoke({"content": "data"})
    assert not result.success


@pytest.mark.asyncio
async def test_list_dir_success() -> None:
    cap = ListDirCapability()
    with tempfile.TemporaryDirectory() as d:
        Path(d, "file_a.txt").write_text("a")
        Path(d, "file_b.txt").write_text("b")
        result = await cap.invoke({"path": d})
        assert result.success
        assert "file_a.txt" in result.data
        assert "file_b.txt" in result.data


@pytest.mark.asyncio
async def test_run_command_success() -> None:
    cap = RunCommandCapability()
    result = await cap.invoke({"command": "echo hello_agent_bridge"})
    assert result.success
    assert "hello_agent_bridge" in result.data


@pytest.mark.asyncio
async def test_run_command_failure() -> None:
    cap = RunCommandCapability()
    result = await cap.invoke({"command": "false"})
    assert not result.success
    assert "exit code" in result.error


@pytest.mark.asyncio
async def test_run_command_timeout() -> None:
    cap = RunCommandCapability()
    result = await cap.invoke({"command": "sleep 5", "timeout": 1})
    assert not result.success
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_run_command_missing_command() -> None:
    cap = RunCommandCapability()
    result = await cap.invoke({})
    assert not result.success
    assert "command" in result.error
