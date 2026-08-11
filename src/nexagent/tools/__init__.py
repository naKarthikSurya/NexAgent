"""Project-scoped tools that can later be exposed to an agent runtime."""

from nexagent.tools.filesystem import FileEntry, FilesystemTool, ProjectFilesystem
from nexagent.tools.shell import (
    CommandExecutionError,
    CommandNotAllowedError,
    ProjectShell,
    ShellResult,
    ShellTool,
    ShellToolError,
)

__all__ = [
    "CommandExecutionError",
    "CommandNotAllowedError",
    "FileEntry",
    "FilesystemTool",
    "ProjectFilesystem",
    "ProjectShell",
    "ShellResult",
    "ShellTool",
    "ShellToolError",
]
