"""Tests for local permission enforcement and approval policy."""

from __future__ import annotations

from collections import UserDict
from collections.abc import Sequence
from typing import Any

import pytest

from nexagent.permissions import (
    ActionRequest,
    ActionType,
    Decision,
    GuardedFilesystem,
    GuardedShell,
    PermissionAuditRecord,
    PermissionDeniedError,
    PermissionPolicy,
    PermissionPolicyError,
)
from nexagent.tools.filesystem import FileEntry, FilesystemTool
from nexagent.tools.shell import ShellResult, ShellTool


class SpyFilesystem:
    """Mock filesystem implementation to verify operations never reach primitives when denied."""

    def __init__(self) -> None:
        self.list_called = False
        self.read_called = False
        self.write_called = False

    def list_files(self, relative_path: str = ".") -> Sequence[FileEntry]:
        self.list_called = True
        return (FileEntry(path="allowed.txt", size_bytes=10),)

    def read_file(self, relative_path: str) -> str:
        self.read_called = True
        return "content"

    def write_file(self, relative_path: str, content: str) -> FileEntry:
        self.write_called = True
        return FileEntry(path=relative_path, size_bytes=len(content))


class SpyShell:
    """Mock shell implementation to verify execution never reaches primitives when denied."""

    def __init__(self) -> None:
        self.execute_called = False

    def execute(self, program: str, args: Sequence[str] = ()) -> ShellResult:
        self.execute_called = True
        return ShellResult(
            command=(program, *tuple(args)),
            exit_code=0,
            stdout="ok",
            stderr="",
        )


def test_permission_policy_auto_approves_reads_by_default() -> None:
    policy = PermissionPolicy(auto_approve_reads=True, default_decision=Decision.DENY)

    req_list = ActionRequest(ActionType.LIST_FILES, ".", {})
    req_read = ActionRequest(ActionType.READ_FILE, "notes.txt", {})

    rec_list = policy.evaluate(req_list)
    rec_read = policy.evaluate(req_read)

    assert rec_list.decision == Decision.ALLOW
    assert rec_read.decision == Decision.ALLOW
    assert len(policy.audit_log) == 2


def test_permission_policy_denies_writes_and_shell_by_default() -> None:
    policy = PermissionPolicy(auto_approve_reads=True, default_decision=Decision.DENY)

    req_write = ActionRequest(ActionType.WRITE_FILE, "notes.txt", {"content_length": 10})
    req_exec = ActionRequest(ActionType.EXECUTE_COMMAND, "python (args_count=1)", {"program": "python"})

    with pytest.raises(PermissionDeniedError) as exc_write:
        policy.evaluate(req_write)

    assert exc_write.value.record.decision == Decision.DENY
    assert isinstance(exc_write.value, PermissionPolicyError)

    with pytest.raises(PermissionDeniedError) as exc_exec:
        policy.evaluate(req_exec)

    assert exc_exec.value.record.decision == Decision.DENY
    assert len(policy.audit_log) == 2


def test_permission_policy_custom_approval_handler() -> None:
    class MockHandler:
        def request_approval(self, request: ActionRequest) -> tuple[Decision, str]:
            if request.target == "allowed.txt":
                return Decision.ALLOW, "Explicitly approved file write."
            return Decision.DENY, "Target not in whitelist."

    policy = PermissionPolicy(approval_handler=MockHandler())

    req_allowed = ActionRequest(ActionType.WRITE_FILE, "allowed.txt", {})
    req_denied = ActionRequest(ActionType.WRITE_FILE, "secret.txt", {})

    rec = policy.evaluate(req_allowed)
    assert rec.decision == Decision.ALLOW
    assert rec.reason == "Approval handler authorized action."

    with pytest.raises(PermissionDeniedError) as exc:
        policy.evaluate(req_denied)

    assert exc.value.record.decision == Decision.DENY
    assert exc.value.record.reason == "Approval handler denied action."


def test_permission_policy_handles_handler_exceptions_and_malformed_returns() -> None:
    class CrashingHandler:
        def request_approval(self, request: ActionRequest) -> tuple[Decision, str]:
            raise ValueError("supersecret_database_password_123")

    class MalformedHandler:
        def request_approval(self, request: ActionRequest) -> Any:
            return "not_a_tuple"

    policy_crash = PermissionPolicy(approval_handler=CrashingHandler())
    policy_malformed = PermissionPolicy(approval_handler=MalformedHandler())  # type: ignore[arg-type]

    req = ActionRequest(ActionType.WRITE_FILE, "test.txt", {})

    with pytest.raises(PermissionDeniedError) as exc_crash:
        policy_crash.evaluate(req)

    assert exc_crash.value.record.reason == "Approval handler raised ValueError."
    assert "supersecret" not in exc_crash.value.record.reason

    with pytest.raises(PermissionDeniedError) as exc_malformed:
        policy_malformed.evaluate(req)

    assert exc_malformed.value.record.reason == "Approval handler returned an invalid decision or reason format."


def test_permission_audit_record_freezes_userdict_and_custom_mappings() -> None:
    policy = PermissionPolicy(auto_approve_reads=True)

    custom_dict = UserDict({"items": UserDict({"key": "val"}), "program": "python"})

    req = ActionRequest(ActionType.LIST_FILES, "notes", custom_dict)
    rec = policy.evaluate(req)

    # Verify top-level details is frozen as mappingproxy
    assert type(rec.request.details).__name__ == "mappingproxy"

    # Attempt mutation on UserDict target
    with pytest.raises(TypeError, match="mappingproxy"):
        rec.request.details["program"] = "evil"  # type: ignore[index]

    with pytest.raises(TypeError, match="mappingproxy"):
        rec.request.details["items"]["key"] = "mutated"  # type: ignore[index]


def test_permission_audit_log_uses_fixed_safe_rationale_strings() -> None:
    class SecretDenyingHandler:
        def request_approval(self, request: ActionRequest) -> tuple[Decision, str]:
            return Decision.DENY, "Bearer supersecret_token_value_999"

    policy = PermissionPolicy(approval_handler=SecretDenyingHandler())
    spy_shell = SpyShell()
    guarded_shell = GuardedShell(spy_shell, policy)

    with pytest.raises(PermissionDeniedError) as exc:
        guarded_shell.execute("python", ["-c", "import sys; token='supersecret_token_value_999'"])

    rec = exc.value.record
    assert rec.request.target == "python (args_count=2)"
    assert rec.request.details == {"program": "python", "args_count": 2}
    assert rec.reason == "Approval handler denied action."
    assert "supersecret" not in rec.request.target
    assert "supersecret" not in rec.reason


def test_guarded_filesystem_protocol_conformance_and_spy_protection() -> None:
    spy_fs = SpyFilesystem()
    policy = PermissionPolicy(auto_approve_reads=True, default_decision=Decision.DENY)

    guarded_fs = GuardedFilesystem(spy_fs, policy)

    assert isinstance(guarded_fs, FilesystemTool)

    # Read operation allowed
    files = guarded_fs.list_files()
    assert spy_fs.list_called is True
    assert len(files) == 1

    # Write operation denied -> spy write_file must NEVER be called
    with pytest.raises(PermissionDeniedError):
        guarded_fs.write_file("new.txt", "data")

    assert spy_fs.write_called is False


def test_guarded_shell_protocol_conformance_and_spy_protection() -> None:
    spy_shell = SpyShell()
    policy = PermissionPolicy(auto_approve_reads=False, default_decision=Decision.DENY)

    guarded_shell = GuardedShell(spy_shell, policy)

    assert isinstance(guarded_shell, ShellTool)

    # Execute operation denied -> spy execute must NEVER be called
    with pytest.raises(PermissionDeniedError):
        guarded_shell.execute("python", ["-c", "print(1)"])

    assert spy_shell.execute_called is False
