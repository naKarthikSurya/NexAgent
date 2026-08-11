"""Safe, project-root-scoped command execution tool for NexAgent."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol, runtime_checkable

DEFAULT_TIMEOUT_SECONDS: float = 30.0
DEFAULT_MAX_OUTPUT_BYTES: int = 100_000

PROHIBITED_SHELL_NAMES: set[str] = {
    "sh",
    "bash",
    "zsh",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
}

SAFE_ENV_VARIABLES: set[str] = {
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "PATHEXT",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "TERM",
    "COMSPEC",
    "WINDIR",
}

FORBIDDEN_ENV_VARIABLES: set[str] = {
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
}


class ShellToolError(RuntimeError):
    """Base error for shell tool operations."""


class CommandNotAllowedError(ShellToolError):
    """Raised when a command alias is unlisted, prohibited, or invalid."""


class CommandExecutionError(ShellToolError):
    """Raised when process creation or execution fails at runtime."""


@dataclass(frozen=True)
class ShellResult:
    """The result of executing a command."""

    command: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    output_exceeded: bool = False


@runtime_checkable
class ShellTool(Protocol):
    """Contract for project-root-scoped command execution."""

    def execute(self, program: str, args: Sequence[str] = ()) -> ShellResult:
        """Execute a command within the project root."""


class ProjectShell:
    """Execute permitted commands strictly within a project root directory."""

    def __init__(
        self,
        project_root: str | Path,
        allowed_executables: Mapping[str, str | Path] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"Project root must be an existing directory: {project_root}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be greater than zero.")

        self._root = root
        self._timeout_seconds = float(timeout_seconds)
        self._max_output_bytes = int(max_output_bytes)

        if allowed_executables is None:
            python_path = Path(sys.executable)
            if not python_path.is_absolute():
                raise ValueError("System Python path is not absolute.")
            allowed = {"python": python_path.resolve(strict=True)}
        else:
            allowed = {}
            for alias, path in allowed_executables.items():
                self._validate_alias(alias)
                raw_path = Path(path)
                if not raw_path.is_absolute():
                    raise ValueError(
                        f"Executable mapping for alias '{alias}' must be an absolute path: {path}"
                    )
                try:
                    resolved_path = raw_path.resolve(strict=True)
                except OSError as error:
                    raise ValueError(
                        f"Executable mapping for alias '{alias}' must be an existing file: {path}"
                    ) from error

                if not resolved_path.is_file():
                    raise ValueError(
                        f"Executable mapping for alias '{alias}' must be an existing file: {path}"
                    )
                if alias in allowed:
                    raise ValueError(f"Duplicate executable alias detected: '{alias}'")
                allowed[alias] = resolved_path

        self._allowed_executables = allowed

    def _validate_alias(self, alias: str) -> None:
        if not isinstance(alias, str) or not alias:
            raise ValueError("Executable alias must be a non-empty string.")
        if "/" in alias or "\\" in alias or "\x00" in alias:
            raise ValueError(
                f"Executable alias cannot contain path separators or NUL bytes: {alias}"
            )
        if alias.lower() in PROHIBITED_SHELL_NAMES:
            raise ValueError(f"Prohibited shell alias cannot be registered: {alias}")

    def execute(self, program: str, args: Sequence[str] = ()) -> ShellResult:
        """Execute a permitted command alias with arguments."""

        if not isinstance(program, str) or not program:
            raise CommandNotAllowedError("Program argument must be a non-empty string alias.")
        if isinstance(args, str) or not isinstance(args, Sequence):
            raise CommandNotAllowedError(
                "Arguments must be a sequence of strings (not a single string)."
            )

        for index, arg in enumerate(args):
            if not isinstance(arg, str):
                raise CommandNotAllowedError(f"Argument at index {index} is not a string.")
            if "\x00" in arg:
                raise CommandNotAllowedError(f"Argument at index {index} contains NUL byte.")

        if "/" in program or "\\" in program or "\x00" in program:
            raise CommandNotAllowedError(
                "Program name cannot contain path separators or NUL bytes."
            )

        if program.lower() in PROHIBITED_SHELL_NAMES:
            raise CommandNotAllowedError(
                f"Direct invocation of shell interpreter is prohibited: {program}"
            )

        if program not in self._allowed_executables:
            raise CommandNotAllowedError(
                f"Command alias '{program}' is not in the allowed executables mapping."
            )

        executable_path = str(self._allowed_executables[program])
        full_command = (program, *tuple(args))
        subprocess_command = (executable_path, *tuple(args))

        env = self._build_sanitized_env()

        try:
            process = subprocess.Popen(
                subprocess_command,
                cwd=self._root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except (OSError, ValueError) as error:
            raise CommandExecutionError(f"Failed to launch command '{program}': {error}") from error

        stdout_bytes, stderr_bytes, timed_out, output_exceeded = self._communicate_bounded(process)

        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        exit_code = process.returncode if not timed_out else None

        return ShellResult(
            command=full_command,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            timed_out=timed_out,
            output_exceeded=output_exceeded,
        )

    def _build_sanitized_env(self) -> dict[str, str]:
        sanitized = {}
        for key, value in os.environ.items():
            upper_key = key.upper()
            if upper_key in FORBIDDEN_ENV_VARIABLES:
                continue
            if (
                "KEY" in upper_key
                or "TOKEN" in upper_key
                or "SECRET" in upper_key
                or "AUTH" in upper_key
                or "PASSWORD" in upper_key
                or "CREDENTIAL" in upper_key
            ):
                continue
            if upper_key in SAFE_ENV_VARIABLES:
                sanitized[key] = value
        return sanitized

    def _communicate_bounded(
        self, process: subprocess.Popen[bytes]
    ) -> tuple[bytes, bytes, bool, bool]:
        start_time = time.monotonic()
        stdout_buf = bytearray()
        stderr_buf = bytearray()

        terminal_reason: str | None = None
        reason_lock = threading.Lock()

        def try_set_terminal_reason(reason: str) -> None:
            nonlocal terminal_reason
            with reason_lock:
                if terminal_reason is None:
                    terminal_reason = reason
                    try:
                        process.kill()
                    except OSError:
                        pass

        def read_stream(stream: IO[bytes] | None, buf: bytearray) -> None:
            if stream is None:
                return
            while True:
                try:
                    chunk = getattr(stream, "read1", stream.read)(4096)
                except (ValueError, OSError):
                    break
                if not chunk:
                    break
                if len(buf) + len(chunk) > self._max_output_bytes:
                    needed = max(0, self._max_output_bytes - len(buf))
                    buf.extend(chunk[:needed])
                    try_set_terminal_reason("output_exceeded")
                    break
                buf.extend(chunk)

        t_out = threading.Thread(target=read_stream, args=(process.stdout, stdout_buf), daemon=True)
        t_err = threading.Thread(target=read_stream, args=(process.stderr, stderr_buf), daemon=True)
        t_out.start()
        t_err.start()

        while process.poll() is None:
            elapsed = time.monotonic() - start_time
            if elapsed > self._timeout_seconds:
                try_set_terminal_reason("timed_out")
                break
            time.sleep(0.01)

        process.wait()
        t_out.join(timeout=1.0)
        t_err.join(timeout=1.0)

        with reason_lock:
            final_reason = terminal_reason

        output_exceeded = final_reason == "output_exceeded"
        timed_out = final_reason == "timed_out"

        return (
            bytes(stdout_buf[: self._max_output_bytes]),
            bytes(stderr_buf[: self._max_output_bytes]),
            timed_out,
            output_exceeded,
        )
