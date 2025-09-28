"""Media post-processing Celery tasks for SEIDRA Ultimate."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from PIL import Image

from core.config import settings
from services.database import DatabaseService
from workers.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(name="workers.media_worker.generate_thumbnail")
def generate_thumbnail(file_path: str, size: int = 256) -> Dict[str, str]:
    if not os.path.exists(file_path):
        logger.warning("Cannot generate thumbnail, file missing: %s", file_path)
        return {"status": "missing", "file_path": file_path}

    with Image.open(file_path) as image:
        image.thumbnail((size, size))

        thumb_dir = settings.thumbnail_directory
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{Path(file_path).stem}_thumb.png"
        image.save(thumb_path)

    logger.info("Thumbnail created for %s", file_path)
    return {"status": "ok", "thumbnail": str(thumb_path)}


@celery_app.task(name="workers.media_worker.extract_media_metadata")
def extract_media_metadata(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"status": "missing", "file_path": file_path}

    stats = os.stat(file_path)
    metadata: Dict[str, Any] = {
        "status": "ok",
        "file_path": file_path,
        "size": stats.st_size,
        "modified_at": datetime.utcfromtimestamp(stats.st_mtime).isoformat(),
    }

    if file_path.lower().endswith((".png", ".jpg", ".jpeg")):
        with Image.open(file_path) as image:
            metadata["width"], metadata["height"] = image.size

    return metadata


@celery_app.task(name="workers.media_worker.sync_media_library")
def sync_media_library() -> Dict[str, Any]:
    media_dir = settings.media_directory
    media_dir.mkdir(parents=True, exist_ok=True)

    files = [path for path in media_dir.rglob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)

    logger.info("Media library sync: %d files, %.2f MB", len(files), total_size / 1024**2)
    return {
        "files": len(files),
        "total_size": total_size,
        "directory": str(media_dir),
    }


@celery_app.task(name="workers.media_worker.optimize_media_asset")
def optimize_media_asset(media_id: str) -> Dict[str, Any]:
    db = DatabaseService()
    try:
        media = db.get_media_by_id(media_id)
        if not media:
            return {"status": "missing", "media_id": media_id}

        metadata = extract_media_metadata(media.file_path)
        if media.user_id:
            db.update_media_item(media_id, user_id=media.user_id, metadata=metadata)
        return {"status": "ok", "media_id": media_id, "metadata": metadata}
    finally:
        db.close()


@celery_app.task(name="workers.media_worker.cleanup_orphan_thumbnails")
def cleanup_orphan_thumbnails() -> Dict[str, Any]:
    thumb_dir = settings.thumbnail_directory
    thumb_dir.mkdir(parents=True, exist_ok=True)

    orphans = []
    for thumb_path in thumb_dir.glob("*_thumb.png"):
        original = settings.media_directory / f"{thumb_path.stem.replace('_thumb', '')}.png"
        if not original.exists():
            thumb_path.unlink(missing_ok=True)
            orphans.append(str(thumb_path))

    logger.info("Cleaned %d orphan thumbnails", len(orphans))
    return {"deleted": len(orphans)}
