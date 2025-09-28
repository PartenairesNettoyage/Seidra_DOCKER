"""Recovery and resilience tasks for SEIDRA Ultimate background jobs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from services.database import DatabaseService, GenerationJob
from workers.celery_app import celery_app
from workers.local_queue import get_local_queue, publish_task_with_local_fallback


logger = logging.getLogger(__name__)


_local_queue = get_local_queue("generation")


def _dispatch(job: GenerationJob, payload: Dict[str, Any]) -> None:
    route = (
        "workers.video_worker.generate_video_task"
        if (job.job_type or "image").lower() == "video"
        else "workers.generation_worker.generate_images_task"
    )
    task = celery_app.tasks.get(route)
    if not task:
        logger.error("Impossible de retrouver la tâche %s pour le job %s", route, job.id)
        return
    publish_task_with_local_fallback(
        task,
        args=[job.id, payload],
        queue=None,
        priority=None,
        metadata={"recovery": True},
        local_queue=_local_queue,
    )


@celery_app.task(name="workers.recovery_worker.resume_stuck_jobs")
def resume_stuck_jobs(older_than_minutes: int = 10) -> Dict[str, Any]:
    logger.info("Scanning for stuck jobs older than %s minutes", older_than_minutes)
    db = DatabaseService()
    try:
        stuck_jobs = db.find_stuck_jobs(older_than_minutes=older_than_minutes)
        requeued = 0
        for job in stuck_jobs:
            payload = db.get_job_payload(job)
            db.reset_job_for_retry(job, reason="stuck")
            _dispatch(job, payload)
            requeued += 1
            logger.info("Requeued stuck job %s (%s)", job.id, job.job_type)
        return {"requeued": requeued, "scanned": len(stuck_jobs)}
    finally:
        db.close()


@celery_app.task(name="workers.recovery_worker.retry_failed_jobs")
def retry_failed_jobs(max_retries: int = 3, lookback_minutes: int = 60) -> Dict[str, Any]:
    logger.info("Retrying failed jobs (max %s retries)", max_retries)
    db = DatabaseService()
    try:
        failed_jobs = db.find_failed_jobs(limit=25, newer_than_minutes=lookback_minutes)
        retried = 0
        for job in failed_jobs:
            recovery = (job.metadata_payload or {}).get("recovery", {})
            retries = recovery.get("retries", 0)
            if retries >= max_retries:
                logger.debug("Skipping job %s due to retry limit", job.id)
                continue
            payload = db.get_job_payload(job)
            db.reset_job_for_retry(job, reason="failed")
            _dispatch(job, payload)
            retried += 1
            logger.info("Retry scheduled for job %s (%s/%s)", job.id, retries + 1, max_retries)
        return {"retried": retried, "inspected": len(failed_jobs)}
    finally:
        db.close()


@celery_app.task(name="workers.recovery_worker.audit_pending_jobs")
def audit_pending_jobs(threshold_minutes: int = 15) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(minutes=threshold_minutes)
    db = DatabaseService()
    try:
        pending_jobs = db.list_pending_jobs(before=cutoff)
        logger.info("Found %d pending jobs awaiting dispatch", len(pending_jobs))
        return {"pending": len(pending_jobs)}
    finally:
        db.close()
