"""Safe, UTF-8 filesystem operations scoped to one project root."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

DEFAULT_MAX_FILE_SIZE_BYTES = 1_000_000


class FilesystemToolError(RuntimeError):
    """Base error for project filesystem operations."""


class PathAccessError(FilesystemToolError):
    """Raised when a requested path is outside the configured project root."""


class FileSizeLimitError(FilesystemToolError):
    """Raised when a text operation exceeds the configured size limit."""


class TextEncodingError(FilesystemToolError):
    """Raised when a file is not valid UTF-8 text."""


@dataclass(frozen=True)
class FileEntry:
    """A file listed or written relative to the configured project root."""

    path: str
    size_bytes: int


@runtime_checkable
class FilesystemTool(Protocol):
    """Contract for project-root-scoped text file operations."""

    def list_files(self, relative_path: str = ".") -> Sequence[FileEntry]:
        """List regular files below a relative project path."""

    def read_file(self, relative_path: str) -> str:
        """Read one UTF-8 text file below the project root."""

    def write_file(self, relative_path: str, content: str) -> FileEntry:
        """Write one UTF-8 text file below the project root."""


class ProjectFilesystem:
    """Perform safe text file operations below an explicit project root."""

    def __init__(
        self,
        project_root: str | Path,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
    ) -> None:
        root = Path(project_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"Project root must be a directory: {project_root}")
        if max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be greater than zero.")

        self._root = root
        self._max_file_size_bytes = max_file_size_bytes

    def list_files(self, relative_path: str = ".") -> tuple[FileEntry, ...]:
        """List regular, non-symlink files below a project-relative directory."""

        directory = self._resolve_path(relative_path)
        if not directory.is_dir():
            raise FilesystemToolError(f"Directory does not exist: {relative_path}")

        entries = []
        for candidate in directory.rglob("*"):
            if candidate.is_symlink() or not candidate.is_file():
                continue
            resolved = self._ensure_inside_root(candidate.resolve(strict=False), relative_path)
            entries.append(
                FileEntry(
                    path=resolved.relative_to(self._root).as_posix(),
                    size_bytes=resolved.stat().st_size,
                )
            )

        return tuple(sorted(entries, key=lambda entry: entry.path))

    def read_file(self, relative_path: str) -> str:
        """Read a size-limited UTF-8 text file below the project root."""

        path = self._resolve_path(relative_path)
        if not path.is_file():
            raise FilesystemToolError(f"File does not exist: {relative_path}")
        self._enforce_size(path.stat().st_size, relative_path)

        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise TextEncodingError(f"File is not valid UTF-8 text: {relative_path}") from error

    def write_file(self, relative_path: str, content: str) -> FileEntry:
        """Write size-limited UTF-8 text below the project root."""

        path = self._resolve_path(relative_path)
        encoded_content = content.encode("utf-8")
        self._enforce_size(len(encoded_content), relative_path)

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as file_handle:
            file_handle.write(content)

        return FileEntry(
            path=path.relative_to(self._root).as_posix(),
            size_bytes=len(encoded_content),
        )

    def _resolve_path(self, relative_path: str) -> Path:
        requested_path = Path(relative_path)
        if requested_path.is_absolute() or requested_path.drive:
            raise PathAccessError("Paths must be relative to the configured project root.")

        try:
            candidate = (self._root / requested_path).resolve(strict=False)
        except OSError as error:
            raise PathAccessError(f"Unable to resolve project path: {relative_path}") from error

        return self._ensure_inside_root(candidate, relative_path)

    def _ensure_inside_root(self, candidate: Path, relative_path: str) -> Path:
        try:
            candidate.relative_to(self._root)
        except ValueError as error:
            raise PathAccessError(
                f"Path must remain within the configured project root: {relative_path}"
            ) from error

        return candidate

    def _enforce_size(self, size_bytes: int, relative_path: str) -> None:
        if size_bytes > self._max_file_size_bytes:
            raise FileSizeLimitError(
                f"File exceeds the {self._max_file_size_bytes}-byte limit: {relative_path}"
            )
