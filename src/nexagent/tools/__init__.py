"""Project-scoped tools that can later be exposed to an agent runtime."""

from nexagent.tools.filesystem import FileEntry, FilesystemTool, ProjectFilesystem

__all__ = ["FileEntry", "FilesystemTool", "ProjectFilesystem"]
