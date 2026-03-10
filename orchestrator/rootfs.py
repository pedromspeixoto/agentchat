import hashlib
import logging
import os
from pathlib import Path
from urllib.parse import urlparse
import boto3

logger = logging.getLogger(__name__)

class RootfsManager:
    def __init__(self, cache_dir: str, s3_bucket: str, s3_region: str) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._s3 = boto3.client("s3", region_name=s3_region)
        self._s3_bucket = s3_bucket

    def download_rootfs(self, image_url: str) -> str:
        url_hash = hashlib.sha256(image_url.encode()).hexdigest()[:16]
        cached_path = self._cache_dir / f"rootfs-{url_hash}.ext4"

        if cached_path.exists():
            logger.info("Using cached rootfs: %s", cached_path)
            return str(cached_path)

        parsed = urlparse(image_url)
        s3_key = parsed.path.lstrip("/")

        logger.info("Downloading rootfs from s3://%s/%s to %s", self._s3_bucket, s3_key, cached_path)
        self._s3.download_file(self._s3_bucket, s3_key, str(cached_path))
        logger.info("Download complete: %s", cached_path)
        return str(cached_path)

    async def create_vm_copy(self, cached_path: str, vm_dir: str) -> str:
        import asyncio

        dest = os.path.join(vm_dir, "rootfs.ext4")
        proc = await asyncio.create_subprocess_exec(
            "cp", "--reflink=auto", cached_path, dest,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to copy rootfs: {stderr.decode()}")
        logger.info("Created VM rootfs copy: %s", dest)
        return dest

    def cleanup(self, vm_dir: str) -> None:
        import shutil

        if os.path.exists(vm_dir):
            shutil.rmtree(vm_dir)
            logger.info("Cleaned up VM directory: %s", vm_dir)