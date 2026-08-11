"""Local, deterministic permission enforcement and audit policy for NexAgent."""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from nexagent.tools.filesystem import FileEntry, FilesystemTool
from nexagent.tools.shell import ShellResult, ShellTool


class ActionType(str, Enum):
    """Categorized action types for permission policy evaluation."""

    READ_FILE = "READ_FILE"
    LIST_FILES = "LIST_FILES"
    WRITE_FILE = "WRITE_FILE"
    EXECUTE_COMMAND = "EXECUTE_COMMAND"


class Decision(str, Enum):
    """Policy decision for an action request."""

    ALLOW = "ALLOW"
    DENY = "DENY"


def _freeze_value(val: Any) -> Any:
    """Recursively freeze any Mapping implementation as MappingProxyType and sequences as tuples."""
    if isinstance(val, Mapping):
        return MappingProxyType({str(k): _freeze_value(v) for k, v in val.items()})
    elif isinstance(val, (list, tuple, set, Sequence)) and not isinstance(val, (str, bytes, bytearray)):
        return tuple(_freeze_value(item) for item in val)
    return val


@dataclass(frozen=True)
class ActionRequest:
    """A requested tool operation submitted for permission policy evaluation."""

    action_type: ActionType
    target: str
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _freeze_value(self.details))


@dataclass(frozen=True)
class PermissionAuditRecord:
    """An immutable audit log entry recording a permission evaluation decision."""

    timestamp: str
    request: ActionRequest
    decision: Decision
    reason: str


class PermissionPolicyError(RuntimeError):
    """Base error for permission policy operations."""


class PermissionDeniedError(PermissionPolicyError):
    """Raised when an action request is denied by permission policy."""

    def __init__(self, record: PermissionAuditRecord) -> None:
        super().__init__(
            f"Permission denied for {record.request.action_type.value} on '{record.request.target}': {record.reason}"
        )
        self.record = record


@runtime_checkable
class ApprovalHandler(Protocol):
    """Callback contract for requesting explicit user approval."""

    def request_approval(self, request: ActionRequest) -> tuple[Decision, str]:
        """Request an approval decision for an action request."""


class PermissionPolicy:
    """Evaluates action requests against configured rules and maintains a safe, deeply immutable audit log."""

    def __init__(
        self,
        auto_approve_reads: bool = True,
        default_decision: Decision = Decision.DENY,
        approval_handler: ApprovalHandler | None = None,
    ) -> None:
        self._auto_approve_reads = auto_approve_reads
        self._default_decision = default_decision
        self._approval_handler = approval_handler
        self._audit_log: list[PermissionAuditRecord] = []
        self._lock = threading.Lock()

    @property
    def audit_log(self) -> tuple[PermissionAuditRecord, ...]:
        """Return a thread-safe immutable snapshot of the audit log history."""
        with self._lock:
            return tuple(self._audit_log)

    def evaluate(self, request: ActionRequest) -> PermissionAuditRecord:
        """Evaluate an action request, record a safe audit entry, and enforce permission."""
        decision, reason = self._determine_decision(request)
        safe_record = self._create_safe_audit_record(request, decision, reason)

        with self._lock:
            self._audit_log.append(safe_record)

        if decision == Decision.DENY:
            raise PermissionDeniedError(safe_record)

        return safe_record

    def _determine_decision(self, request: ActionRequest) -> tuple[Decision, str]:
        is_read = request.action_type in (ActionType.READ_FILE, ActionType.LIST_FILES)
        if is_read and self._auto_approve_reads:
            return Decision.ALLOW, "Auto-approved read operation."

        if self._approval_handler is not None:
            try:
                result = self._approval_handler.request_approval(request)
                if isinstance(result, tuple) and len(result) == 2:
                    handler_decision, _ = result
                    if isinstance(handler_decision, Decision):
                        if handler_decision == Decision.ALLOW:
                            return Decision.ALLOW, "Approval handler authorized action."
                        return Decision.DENY, "Approval handler denied action."
                return Decision.DENY, "Approval handler returned an invalid decision or reason format."
            except Exception as error:
                return Decision.DENY, f"Approval handler raised {type(error).__name__}."

        if self._default_decision == Decision.ALLOW:
            return Decision.ALLOW, "Default policy set to ALLOW."

        return Decision.DENY, "Default policy set to DENY."

    def _create_safe_audit_record(
        self, request: ActionRequest, decision: Decision, reason: str
    ) -> PermissionAuditRecord:
        now_utc = datetime.now(timezone.utc).isoformat()

        if request.action_type == ActionType.EXECUTE_COMMAND:
            program = str(
                request.details.get(
                    "program", request.target.split()[0] if request.target else "unknown"
                )
            )
            raw_args = request.details.get("args", ())
            args_count = (
                request.details.get("args_count")
                if "args_count" in request.details
                else (len(raw_args) if isinstance(raw_args, Sequence) else 0)
            )
            safe_target = f"{program} (args_count={args_count})"
            safe_details = _freeze_value({"program": program, "args_count": args_count})
        elif request.action_type in (ActionType.WRITE_FILE, ActionType.READ_FILE, ActionType.LIST_FILES):
            safe_target = request.target
            safe_details_raw = {}
            for k, v in request.details.items():
                if k == "content":
                    continue
                safe_details_raw[k] = v
            safe_details = _freeze_value(safe_details_raw)
        else:
            safe_target = request.target
            safe_details = _freeze_value(request.details)

        safe_request = ActionRequest(
            action_type=request.action_type,
            target=safe_target,
            details=safe_details,
        )

        return PermissionAuditRecord(
            timestamp=now_utc,
            request=safe_request,
            decision=decision,
            reason=reason,
        )


class GuardedFilesystem:
    """Wraps a FilesystemTool, enforcing PermissionPolicy evaluation on all operations."""

    def __init__(self, filesystem: FilesystemTool, policy: PermissionPolicy) -> None:
        self._filesystem = filesystem
        self._policy = policy

    def list_files(self, relative_path: str = ".") -> Sequence[FileEntry]:
        """List files below project root, subject to policy evaluation."""
        request = ActionRequest(
            action_type=ActionType.LIST_FILES,
            target=relative_path,
            details={"relative_path": relative_path},
        )
        self._policy.evaluate(request)
        return self._filesystem.list_files(relative_path)

    def read_file(self, relative_path: str) -> str:
        """Read a file below project root, subject to policy evaluation."""
        request = ActionRequest(
            action_type=ActionType.READ_FILE,
            target=relative_path,
            details={"relative_path": relative_path},
        )
        self._policy.evaluate(request)
        return self._filesystem.read_file(relative_path)

    def write_file(self, relative_path: str, content: str) -> FileEntry:
        """Write a file below project root, subject to policy evaluation."""
        request = ActionRequest(
            action_type=ActionType.WRITE_FILE,
            target=relative_path,
            details={"relative_path": relative_path, "content_length": len(content)},
        )
        self._policy.evaluate(request)
        return self._filesystem.write_file(relative_path, content)


class GuardedShell:
    """Wraps a ShellTool, enforcing PermissionPolicy evaluation on all executions."""

    def __init__(self, shell: ShellTool, policy: PermissionPolicy) -> None:
        self._shell = shell
        self._policy = policy

    def execute(self, program: str, args: Sequence[str] = ()) -> ShellResult:
        """Execute a permitted command alias, subject to policy evaluation."""
        cmd_target = f"{program} (args_count={len(args)})"
        request = ActionRequest(
            action_type=ActionType.EXECUTE_COMMAND,
            target=cmd_target,
            details={"program": program, "args": tuple(args), "args_count": len(args)},
        )
        self._policy.evaluate(request)
        return self._shell.execute(program, args)
