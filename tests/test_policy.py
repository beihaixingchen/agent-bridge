"""Tests for the policy enforcer: the core authorization layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_bridge.policy.enforcer import Enforcer
from agent_bridge.policy.models import CapabilityConstraint, CapabilityGrant
from agent_bridge.policy.store import GrantStore


def _make_enforcer() -> tuple[Enforcer, GrantStore]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        store = GrantStore(Path(f.name))
    return Enforcer(store, default="deny"), store


def test_local_caller_bypasses_policy() -> None:
    enforcer, _ = _make_enforcer()
    decision = enforcer.check(None, "read_file", {"path": "/etc/passwd"})
    assert decision.allowed
    assert "local" in decision.reason


def test_mesh_peer_cannot_invoke_capabilities() -> None:
    enforcer, _ = _make_enforcer()
    decision = enforcer.check("mesh-peer", "read_file", {"path": "/tmp/x"})
    assert not decision.allowed


def test_unknown_agent_denied() -> None:
    enforcer, _ = _make_enforcer()
    decision = enforcer.check("stranger", "read_file", {"path": "/tmp/x"})
    assert not decision.allowed
    assert "no grants" in decision.reason


def test_granted_capability_allowed() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant("alice", "read_file", CapabilityGrant(allowed=True))
    decision = enforcer.check("alice", "read_file", {"path": "/tmp/x"})
    assert decision.allowed


def test_ungranted_capability_denied() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant("alice", "read_file", CapabilityGrant(allowed=True))
    decision = enforcer.check("alice", "run_command", {"command": "ls"})
    assert not decision.allowed
    assert "not granted" in decision.reason


def test_explicit_deny() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant("alice", "read_file", CapabilityGrant(allowed=False))
    decision = enforcer.check("alice", "read_file", {"path": "/tmp/x"})
    assert not decision.allowed
    assert "denied" in decision.reason


def test_path_prefix_constraint_allows_within() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant(
        "alice",
        "read_file",
        CapabilityGrant(
            allowed=True,
            constraints=CapabilityConstraint(path_prefix="/tmp/"),
        ),
    )
    decision = enforcer.check("alice", "read_file", {"path": "/tmp/data.txt"})
    assert decision.allowed


def test_path_prefix_constraint_denies_outside() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant(
        "alice",
        "read_file",
        CapabilityGrant(
            allowed=True,
            constraints=CapabilityConstraint(path_prefix="/tmp/"),
        ),
    )
    decision = enforcer.check("alice", "read_file", {"path": "/etc/passwd"})
    assert not decision.allowed
    assert "outside" in decision.reason


def test_command_allowlist_allows() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant(
        "bob",
        "run_command",
        CapabilityGrant(
            allowed=True,
            constraints=CapabilityConstraint(allowed_commands=["ls", "cat"]),
        ),
    )
    decision = enforcer.check("bob", "run_command", {"command": "ls -la /tmp"})
    assert decision.allowed


def test_command_allowlist_denies() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant(
        "bob",
        "run_command",
        CapabilityGrant(
            allowed=True,
            constraints=CapabilityConstraint(allowed_commands=["ls", "cat"]),
        ),
    )
    decision = enforcer.check("bob", "run_command", {"command": "rm -rf /"})
    assert not decision.allowed


def test_no_constraint_means_unrestricted() -> None:
    enforcer, store = _make_enforcer()
    store.set_grant(
        "alice", "read_file", CapabilityGrant(allowed=True)
    )
    # No path_prefix set — any path is allowed
    decision = enforcer.check("alice", "read_file", {"path": "/etc/passwd"})
    assert decision.allowed
