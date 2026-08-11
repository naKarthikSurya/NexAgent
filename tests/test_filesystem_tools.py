"""Tests for project-root-scoped filesystem tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexagent.tools.filesystem import (
    FileSizeLimitError,
    FilesystemTool,
    PathAccessError,
    ProjectFilesystem,
    TextEncodingError,
)


def test_project_filesystem_lists_reads_and_writes_utf8_text(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    written = filesystem.write_file("notes/todo.txt", "Ship the foundation.\n")

    assert isinstance(filesystem, FilesystemTool)
    assert written.path == "notes/todo.txt"
    assert written.size_bytes == len("Ship the foundation.\n".encode("utf-8"))
    assert filesystem.read_file("notes/todo.txt") == "Ship the foundation.\n"
    assert filesystem.list_files() == (written,)


@pytest.mark.parametrize("relative_path", ["../outside.txt", "nested/../../outside.txt"])
def test_project_filesystem_rejects_path_traversal(tmp_path: Path, relative_path: str) -> None:
    filesystem = ProjectFilesystem(tmp_path)

    with pytest.raises(PathAccessError, match="within the configured project root"):
        filesystem.write_file(relative_path, "blocked")


def test_project_filesystem_rejects_absolute_paths(tmp_path: Path) -> None:
    filesystem = ProjectFilesystem(tmp_path)
    outside_path = tmp_path.parent / "outside.txt"

    with pytest.raises(PathAccessError, match="relative"):
        filesystem.read_file(str(outside_path))


def test_project_filesystem_rejects_symlink_escapes(tmp_path: Path) -> None:
    outside_path = tmp_path.parent / "outside.txt"
    outside_path.write_text("outside", encoding="utf-8")
    escape_path = tmp_path / "escape.txt"

    try:
        escape_path.symlink_to(outside_path)
    except OSError as error:
        pytest.skip(f"Symlinks are unavailable in this environment: {error}")

    filesystem = ProjectFilesystem(tmp_path)

    with pytest.raises(PathAccessError, match="within the configured project root"):
        filesystem.read_file("escape.txt")
    with pytest.raises(PathAccessError, match="within the configured project root"):
        filesystem.write_file("escape.txt", "blocked")
    assert filesystem.list_files() == ()


def test_project_filesystem_rejects_invalid_utf8_and_oversized_text(tmp_path: Path) -> None:
    (tmp_path / "invalid.txt").write_bytes(b"\xff")
    (tmp_path / "large.txt").write_text("12345", encoding="utf-8")
    filesystem = ProjectFilesystem(tmp_path, max_file_size_bytes=4)

    with pytest.raises(TextEncodingError, match="UTF-8"):
        filesystem.read_file("invalid.txt")
    with pytest.raises(FileSizeLimitError, match="4-byte limit"):
        filesystem.read_file("large.txt")
    with pytest.raises(FileSizeLimitError, match="4-byte limit"):
        filesystem.write_file("new.txt", "12345")
