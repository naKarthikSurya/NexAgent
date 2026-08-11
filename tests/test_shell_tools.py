"""Tests for project-root-scoped shell execution tools."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from nexagent.tools.shell import (
    CommandNotAllowedError,
    ProjectShell,
    ShellResult,
    ShellTool,
)


def test_project_shell_valid_execution(tmp_path: Path) -> None:
    shell = ProjectShell(tmp_path)

    assert isinstance(shell, ShellTool)

    result = shell.execute("python", ["-c", "print('hello from shell')"])

    assert isinstance(result, ShellResult)
    assert result.command == ("python", "-c", "print('hello from shell')")
    assert result.exit_code == 0
    assert result.stdout == "hello from shell\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.output_exceeded is False


def test_project_shell_invalid_configuration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Project root must be an existing directory"):
        ProjectShell(tmp_path / "non_existent")

    with pytest.raises(ValueError, match="must be an absolute path"):
        ProjectShell(tmp_path, allowed_executables={"py": "relative_python"})

    with pytest.raises(ValueError, match="must be an absolute path"):
        relative_py = os.path.relpath(sys.executable, start=tmp_path)
        ProjectShell(tmp_path, allowed_executables={"py": relative_py})

    with pytest.raises(ValueError, match="must be an existing file"):
        missing_abs = (tmp_path / "missing_binary.exe").resolve()
        ProjectShell(tmp_path, allowed_executables={"py": missing_abs})

    with pytest.raises(ValueError, match="Prohibited shell alias"):
        ProjectShell(tmp_path, allowed_executables={"bash": sys.executable})

    with pytest.raises(ValueError, match="cannot contain path separators"):
        ProjectShell(tmp_path, allowed_executables={"sub/dir": sys.executable})

    with pytest.raises(ValueError, match="greater than zero"):
        ProjectShell(tmp_path, timeout_seconds=0)

    with pytest.raises(ValueError, match="greater than zero"):
        ProjectShell(tmp_path, max_output_bytes=-5)


def test_project_shell_rejects_paths_nul_and_non_string_args(tmp_path: Path) -> None:
    shell = ProjectShell(tmp_path)

    with pytest.raises(CommandNotAllowedError, match="cannot contain path separators"):
        shell.execute("../python")

    with pytest.raises(CommandNotAllowedError, match="cannot contain path separators"):
        shell.execute("py\\thon")

    with pytest.raises(CommandNotAllowedError, match="cannot contain path separators"):
        shell.execute("python\x00")

    with pytest.raises(CommandNotAllowedError, match="contains NUL byte"):
        shell.execute("python", ["-c\x00"])

    with pytest.raises(CommandNotAllowedError, match="non-empty string alias"):
        shell.execute("", ["-c", "print(1)"])  # type: ignore[arg-type]

    with pytest.raises(CommandNotAllowedError, match="sequence of strings"):
        shell.execute("python", "-c print(1)")  # type: ignore[arg-type]

    with pytest.raises(CommandNotAllowedError, match="is not a string"):
        shell.execute("python", [123])  # type: ignore[list-item]

    with pytest.raises(CommandNotAllowedError, match="Direct invocation of shell"):
        shell.execute("cmd.exe")

    with pytest.raises(CommandNotAllowedError, match="not in the allowed executables"):
        shell.execute("custom_tool")


def test_project_shell_minimal_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "/custom/python/path")
    monkeypatch.setenv("LD_PRELOAD", "/custom/lib.so")
    monkeypatch.setenv("MY_SECRET_TOKEN", "supersecret123")
    monkeypatch.setenv("API_KEY", "key_abc123")

    shell = ProjectShell(tmp_path)

    code = (
        "import os, json; "
        "env = dict(os.environ); "
        "print(json.dumps({"
        "'has_pythonpath': 'PYTHONPATH' in env, "
        "'has_ld_preload': 'LD_PRELOAD' in env, "
        "'has_secret': 'MY_SECRET_TOKEN' in env, "
        "'has_api_key': 'API_KEY' in env"
        "}))"
    )

    result = shell.execute("python", ["-c", code])
    assert result.exit_code == 0
    assert '"has_pythonpath": false' in result.stdout
    assert '"has_ld_preload": false' in result.stdout
    assert '"has_secret": false' in result.stdout
    assert '"has_api_key": false' in result.stdout


def test_project_shell_working_directory_containment(tmp_path: Path) -> None:
    sub_dir = tmp_path / "workspace"
    sub_dir.mkdir()

    shell = ProjectShell(sub_dir)

    code = "import os, pathlib; print(pathlib.Path(os.getcwd()).resolve())"
    result = shell.execute("python", ["-c", code])

    assert result.exit_code == 0
    assert result.stdout.strip() == str(sub_dir.resolve())


def test_project_shell_non_zero_exit_capture(tmp_path: Path) -> None:
    shell = ProjectShell(tmp_path)

    code = "import sys; sys.stderr.write('error log\\n'); sys.exit(42)"
    result = shell.execute("python", ["-c", code])

    assert result.exit_code == 42
    assert result.stdout == ""
    assert result.stderr == "error log\n"
    assert result.timed_out is False
    assert result.output_exceeded is False


def test_project_shell_timeout_behavior(tmp_path: Path) -> None:
    shell = ProjectShell(tmp_path, timeout_seconds=0.2)

    code = "import time; time.sleep(2.0)"
    result = shell.execute("python", ["-c", code])

    assert result.exit_code is None
    assert result.timed_out is True
    assert result.output_exceeded is False


def test_project_shell_stdout_and_stderr_overflow_limits(tmp_path: Path) -> None:
    shell = ProjectShell(tmp_path, max_output_bytes=50)

    # Stdout overflow test
    result_out = shell.execute("python", ["-c", "print('A' * 500)"])
    assert result_out.output_exceeded is True
    assert result_out.timed_out is False
    assert len(result_out.stdout.encode("utf-8")) <= 50

    # Stderr overflow test
    result_err = shell.execute("python", ["-c", "import sys; sys.stderr.write('B' * 500)"])
    assert result_err.output_exceeded is True
    assert result_err.timed_out is False
    assert len(result_err.stderr.encode("utf-8")) <= 50

    # Mixed stdout and stderr test
    result_mix = shell.execute(
        "python", ["-c", "import sys; sys.stdout.write('O' * 30); sys.stderr.write('E' * 30)"]
    )
    assert result_mix.exit_code == 0
    assert result_mix.output_exceeded is False
    assert result_mix.timed_out is False
    assert result_mix.stdout == "O" * 30
    assert result_mix.stderr == "E" * 30


def test_project_shell_flush_then_sleep_output_limit(tmp_path: Path) -> None:
    shell = ProjectShell(tmp_path, timeout_seconds=10.0, max_output_bytes=50)

    # Child writes 500 bytes, flushes stdout, then sleeps
    code = "import sys, time; sys.stdout.write('A' * 500); sys.stdout.flush(); time.sleep(15.0)"

    result = shell.execute("python", ["-c", code])

    assert result.output_exceeded is True
    assert result.timed_out is False
    assert len(result.stdout.encode("utf-8")) <= 50
