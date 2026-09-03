from functools import lru_cache

from app.core.config import get_settings
from app.providers.storage.base import StorageProvider
from app.providers.storage.local import LocalStorageProvider


@lru_cache
def get_storage_provider() -> StorageProvider:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorageProvider(settings.storage_local_path)
    raise ValueError(
        f"Unknown STORAGE_BACKEND '{settings.storage_backend}'. "
        "Only 'local' is implemented — implement StorageProvider for S3 and wire it in here to add it."
    )
