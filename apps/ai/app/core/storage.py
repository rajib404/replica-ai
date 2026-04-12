import logging
import shutil
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class FileStorage:
    """Local filesystem storage for knowledge ingestion files."""

    def __init__(self, base_path: str | None = None) -> None:
        self._base = Path(base_path or settings.storage_base_path)

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
        """Remove all files for a given knowledge entry."""
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
