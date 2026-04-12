"""Minimal local file storage for voice profiles.

Knowledge ingestion file storage has moved to apps/ai.
This module retains only what's needed for voice profile .npy files.
"""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_VOICE_STORAGE_PATH = "./storage"


class FileStorage:
    """Local filesystem storage for voice profile files."""

    def __init__(self, base_path: str | None = None) -> None:
        self._base = Path(base_path or _VOICE_STORAGE_PATH)

    def _entry_dir(self, owner_id: str, content_type: str, entry_id: str) -> Path:
        return self._base / owner_id / content_type / entry_id

    def save_file(
        self,
        owner_id: str,
        content_type: str,
        entry_id: str,
        filename: str,
        data: bytes,
    ) -> str:
        """Save file bytes to disk. Returns the relative path string."""
        directory = self._entry_dir(owner_id, content_type, entry_id)
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / filename
        filepath.write_bytes(data)
        return str(filepath.relative_to(self._base))

    def read_file(self, relative_path: str) -> bytes:
        """Read a file by its stored relative path."""
        return (self._base / relative_path).read_bytes()

    def delete_entry_files(self, owner_id: str, content_type: str, entry_id: str) -> None:
        """Remove all files for a given entry."""
        directory = self._entry_dir(owner_id, content_type, entry_id)
        if directory.exists():
            shutil.rmtree(directory)
            logger.info("Deleted files for entry %s", entry_id)


_file_storage: FileStorage | None = None


def get_storage() -> FileStorage:
    global _file_storage
    if _file_storage is None:
        _file_storage = FileStorage()
    return _file_storage
