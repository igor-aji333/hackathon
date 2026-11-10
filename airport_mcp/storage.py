"""Persistent key/value storage for cached FAA data files (local disk or S3)."""

import logging
from pathlib import Path
from typing import Optional, Protocol

from .config import Settings, StorageBackend

logger = logging.getLogger(__name__)


class ArtifactStore(Protocol):
    """Minimal blob store: `read` returns None when the artifact does not exist."""

    def read(self, name: str) -> Optional[bytes]: ...

    def write(self, name: str, data: bytes) -> None: ...


class LocalArtifactStore:
    def __init__(self, root: Path):
        self.root = root

    def read(self, name: str) -> Optional[bytes]:
        path = self.root / name
        return path.read_bytes() if path.is_file() else None

    def write(self, name: str, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / name
        # Write-then-rename so a crash never leaves a truncated cache file behind.
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)
        logger.info("Wrote %s (%d bytes)", path, len(data))


class S3ArtifactStore:
    def __init__(self, bucket: str, prefix: str = "", client=None):
        self.bucket = bucket
        self.prefix = prefix
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3  # optional dependency: pip install "airport-mcp[s3]"

            self._client = boto3.client("s3")
        return self._client

    def _key(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def read(self, name: str) -> Optional[bytes]:
        from botocore.exceptions import ClientError

        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(name))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                return None
            raise
        return obj["Body"].read()

    def write(self, name: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(name), Body=data)
        logger.info("Wrote s3://%s/%s (%d bytes)", self.bucket, self._key(name), len(data))


def create_store(settings: Settings) -> ArtifactStore:
    if settings.storage_backend is StorageBackend.S3:
        return S3ArtifactStore(bucket=settings.s3_bucket, prefix=settings.s3_prefix)
    return LocalArtifactStore(settings.local_data_dir)
