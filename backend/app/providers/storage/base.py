"""Storage provider interface.

Ticket files must never be publicly exposed (project rule). This
abstraction keeps ticket_service from touching the filesystem directly,
so storage can move to S3 (or anything else, e.g. private object storage
with signed URLs) later without changing calling code — and so that
"where ticket files live" stays a single, auditable decision point.
"""
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    async def save(self, key: str, content: bytes, content_type: str) -> str:
        """Persists content under `key`. Returns the storage key actually used."""

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """Raises FileNotFoundError if the key doesn't exist."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """No-op if the key doesn't exist."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...
