"""MinIO storage client for artifact uploads."""
import asyncio
import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        try:
            if not _client.bucket_exists(settings.MINIO_BUCKET):
                _client.make_bucket(settings.MINIO_BUCKET)
                logger.info(f"Created MinIO bucket: {settings.MINIO_BUCKET}")
        except S3Error as e:
            logger.error(f"MinIO bucket setup error: {e}")
    return _client


def _upload_sync(object_name: str, data: bytes) -> str:
    """Sync MinIO upload + presigned URL. Runs in thread pool."""
    client = _get_client()
    client.put_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
        data=io.BytesIO(data),
        length=len(data),
    )
    url = client.presigned_get_object(
        bucket_name=settings.MINIO_BUCKET,
        object_name=object_name,
        expires=timedelta(days=7),
    )
    return url


async def upload_artifact(session_id: str, artifact_id: str, name: str, data: bytes) -> tuple[str, str]:
    """Upload artifact bytes to MinIO. Returns (minio_path, presigned_url)."""
    object_name = f"artifacts/{session_id}/{artifact_id}/{name}"
    url = await asyncio.to_thread(_upload_sync, object_name, data)
    logger.info(f"Uploaded artifact to MinIO: {object_name}")
    return object_name, url
