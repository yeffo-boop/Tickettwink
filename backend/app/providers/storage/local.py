"""Local filesystem storage provider.

Files are written under STORAGE_LOCAL_PATH, OUTSIDE any directory served
statically by FastAPI/nginx — there is intentionally no static file mount
for this directory anywhere in the app (see deploy/nginx template and
main.py). The only way to read a ticket file back out is through the
authenticated `/api/tickets/{id}/file` route, which checks that the
requesting user owns the ticket or is an admin before calling
`StorageProvider.read()`. Do not add a static mount for this path.
"""
import os
from pathlib import Path

from app.providers.storage.base import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, base_path: str):
        self._base_path = Path(base_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Prevent path traversal outside the storage root.
        candidate = (self._base_path / key).resolve()
        if not str(candidate).startswith(str(self._base_path)):
            raise ValueError(f"Invalid storage key: {key!r}")
        return candidate

    async def save(self, key: str, content: bytes, content_type: str) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_bytes(content)
        os.replace(tmp_path, path)  # atomic on same filesystem
        return key

    async def read(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()
