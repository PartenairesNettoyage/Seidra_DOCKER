"""Celery tasks responsible for video orchestration (SadTalker, ComfyUI)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from services.database import DatabaseService
from services.generation_service import get_generation_service
from workers.celery_app import celery_app


logger = logging.getLogger(__name__)
_generation_service = get_generation_service()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120, name="workers.video_worker.generate_video_task")
def generate_video_task(self, job_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("Starting video generation job %s", job_id)
    db = DatabaseService()
    try:
        db.update_job(job_id, status="processing", progress=0.0)
    finally:
        db.close()

    try:
        result = _generation_service.process_video_job_sync(job_id, request_data)
        logger.info("Video job %s completed", job_id)

        try:
            from workers.media_worker import extract_media_metadata

            for path in result.get("result_videos", []):
                extract_media_metadata.delay(path)
        except Exception:  # pragma: no cover - metadata extraction is optional
            logger.debug("Metadata extraction worker unavailable for %s", job_id)

        return result
    except Exception as exc:  # pragma: no cover - executed only with Celery
        logger.exception("Video job %s failed", job_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120)
        raise


@celery_app.task(name="workers.video_worker.queue_video_generation")
def queue_video_generation(job_id: str, request_data: Dict[str, Any]) -> str:
    generate_video_task.delay(job_id, request_data)
    return job_id


@celery_app.task(name="workers.video_worker.notify_video_ready")
def notify_video_ready(job_id: str, asset_path: str) -> Dict[str, str]:
    db = DatabaseService()
    try:
        db.update_job(job_id, status="completed")
    finally:
        db.close()

    logger.info("Video asset ready for job %s: %s", job_id, asset_path)
    return {"job_id": job_id, "asset_path": asset_path}


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=90,
    name="workers.video_worker.generate_timeline_proxy",
)
def generate_timeline_proxy_task(
    self,
    job_id: str,
    timeline_id: str,
    user_id: int,
    force: bool = False,
) -> Dict[str, Any]:
    try:
        return _generation_service.generate_timeline_proxy_sync(
            job_id,
            timeline_id,
            user_id,
            force=force,
        )
    except Exception as exc:  # pragma: no cover - depends on Celery runtime
        logger.exception(
            "Timeline proxy generation failed (timeline=%s job=%s)", timeline_id, job_id
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        raise


@celery_app.task(name="workers.video_worker.generate_asset_waveform")
def generate_asset_waveform_task(
    asset_id: str, sample_points: int = 128, force: bool = False
) -> Dict[str, Any]:
    logger.info(
        "Generating waveform for asset %s (samples=%d force=%s)",
        asset_id,
        sample_points,
        force,
    )
    return _generation_service.generate_asset_waveform_sync(
        asset_id,
        sample_points=sample_points,
        force=force,
    )
