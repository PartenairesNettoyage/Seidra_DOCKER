"""Celery tasks dedicated to image generation orchestration."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
import time
from typing import Any, Dict, List, Tuple

from services.database import DatabaseService, GenerationJob
from services.generation_service import (
    GenerationService,
    GPUUnavailableError,
    get_generation_service,
)
from workers.celery_app import celery_app
from workers.local_queue import (
    LocalQueueEntry,
    get_local_queue,
    publish_task_with_local_fallback,
)


logger = logging.getLogger(__name__)
_generation_service = get_generation_service()
_local_queue = get_local_queue("generation")
_PUBLISH_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 1,
    "interval_step": 2,
    "interval_max": 10,
}


QUEUE_REALTIME = "generation.realtime"
QUEUE_BATCH = "generation.batch"
QUEUE_NAME_BY_TAG = {
    "realtime": QUEUE_REALTIME,
    "batch": QUEUE_BATCH,
}


def _resolve_queue_config(priority_tag: str) -> Tuple[str, int]:
    queue_tag = GenerationService.resolve_priority_queue_tag(priority_tag)
    normalized = (priority_tag or "normal").lower()
    priority_value = GenerationService.PRIORITY_MAP.get(
        normalized, GenerationService.PRIORITY_MAP["normal"]
    )
    queue_name = QUEUE_NAME_BY_TAG[queue_tag]
    return queue_name, max(0, min(9, priority_value))


def _dispatch_local_entry(entry: LocalQueueEntry) -> bool:
    task = celery_app.tasks.get(entry.task_name)
    if not task:
        logger.error("Tâche inconnue dans la file locale: %s", entry.task_name)
        return True
    options: Dict[str, Any] = {}
    if entry.queue:
        options["queue"] = entry.queue
    if entry.priority is not None:
        options["priority"] = entry.priority
    if entry.metadata:
        options.setdefault("headers", {})
        options["headers"].update(entry.metadata)
    try:
        task.apply_async(
            args=entry.args,
            kwargs=entry.kwargs,
            retry=True,
            retry_policy=_PUBLISH_RETRY_POLICY,
            **options,
        )
        return True
    except Exception as exc:  # pragma: no cover - dépend du broker
        logger.warning(
            "Réémission Celery échouée pour %s depuis la file locale: %s",
            entry.task_name,
            exc,
        )
        entry.last_error = str(exc)
        time.sleep(0.5)
        return False


def _drain_local_queue(max_items: int = 50) -> Dict[str, int]:
    result = _local_queue.drain(_dispatch_local_entry, max_items=max_items)
    if result["dispatched"]:
        logger.info(
            "%d tâche(s) rejouée(s) depuis la file locale génération", result["dispatched"]
        )
    if result["remaining"]:
        logger.debug(
            "%d tâche(s) restent dans la file locale génération",
            result["remaining"],
        )
    return result


def submit_generation_job(
    job_id: str,
    request_data: Dict[str, Any],
    priority_tag: str = "realtime",
    *,
    countdown: int = 0,
) -> str:
    queue_name, priority = _resolve_queue_config(priority_tag)
    _drain_local_queue()
    published = publish_task_with_local_fallback(
        generate_images_task,
        args=[job_id, request_data, priority_tag],
        queue=queue_name,
        priority=priority,
        countdown=countdown,
        metadata={"priority_tag": priority_tag},
        local_queue=_local_queue,
        retry_policy=_PUBLISH_RETRY_POLICY,
    )
    if not published:
        logger.warning(
            "Tâche %s stockée localement (job=%s priority=%s)",
            generate_images_task.name,
            job_id,
            priority_tag,
        )
    return job_id


def submit_batch_generation_job(
    job_ids: List[str],
    requests_data: List[Dict[str, Any]],
    priority_tag: str = "batch",
    *,
    countdown: int = 0,
) -> List[str]:
    queue_name, priority = _resolve_queue_config(priority_tag)
    _drain_local_queue()
    published = publish_task_with_local_fallback(
        batch_generate_images_task,
        args=[job_ids, requests_data, priority_tag],
        queue=queue_name,
        priority=priority,
        countdown=countdown,
        metadata={"priority_tag": priority_tag, "batch": True},
        local_queue=_local_queue,
        retry_policy=_PUBLISH_RETRY_POLICY,
    )
    if not published:
        logger.warning(
            "Batch %s stocké localement (%d jobs, priority=%s)",
            batch_generate_images_task.name,
            len(job_ids),
            priority_tag,
        )
    return job_ids


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=int(GenerationService.DEGRADED_BACKOFF_SECONDS),
    name="workers.generation_worker.generate_images_task",
)
def generate_images_task(
    self, job_id: str, request_data: Dict[str, Any], priority_tag: str = "realtime"
) -> Dict[str, Any]:
    logger.info("Starting generation job %s", job_id)
    db = DatabaseService()
    try:
        db.update_job(job_id, status="processing", progress=0.0)
    finally:
        db.close()

    try:
        result = _generation_service.process_job_sync(
            job_id, request_data, priority_tag=priority_tag
        )
        logger.info("Generation job %s completed", job_id)
        return result
    except GPUUnavailableError as exc:
        logger.warning("GPU unavailable for job %s, retrying: %s", job_id, exc)
        raise self.retry(exc=exc, countdown=int(GenerationService.DEGRADED_BACKOFF_SECONDS))
    except Exception as exc:  # pragma: no cover - executed only with Celery
        logger.exception("Generation job %s failed", job_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
        raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=int(GenerationService.DEGRADED_BACKOFF_SECONDS),
    name="workers.generation_worker.batch_generate_images_task",
)
def batch_generate_images_task(
    self,
    job_ids: List[str],
    requests_data: List[Dict[str, Any]],
    priority_tag: str = "batch",
) -> Dict[str, Any]:
    logger.info("Processing batch generation for %d jobs", len(job_ids))
    results: List[Dict[str, Any]] = []
    failed: List[Dict[str, str]] = []

    for job_id, data in zip(job_ids, requests_data):
        try:
            results.append(
                _generation_service.process_job_sync(
                    job_id, data, priority_tag=priority_tag
                )
            )
        except GPUUnavailableError as exc:
            logger.warning(
                "GPU unavailable for batch job %s, rescheduling: %s",
                job_id,
                exc,
            )
            submit_generation_job(
                job_id,
                data,
                priority_tag=priority_tag,
                countdown=int(GenerationService.DEGRADED_BACKOFF_SECONDS),
            )
            failed.append(
                {"job_id": job_id, "error": str(exc), "action": "requeued"}
            )
        except Exception as exc:  # pragma: no cover - requires Celery runtime
            logger.exception("Batch job %s failed", job_id)
            failed.append({"job_id": job_id, "error": str(exc)})

    return {"results": results, "failed": failed}


@celery_app.task(name="workers.generation_worker.cleanup_old_jobs")
def cleanup_old_jobs() -> Dict[str, Any]:
    logger.info("Cleaning up completed jobs older than 30 days")
    db = DatabaseService()
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)
        deleted = (
            db.db.query(GenerationJob)
            .filter(GenerationJob.completed_at.isnot(None))
            .filter(GenerationJob.completed_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.db.commit()
        logger.info("Removed %d historical jobs", deleted)
        return {"deleted": deleted}
    except Exception as exc:  # pragma: no cover
        db.db.rollback()
        logger.exception("Cleanup failed")
        return {"deleted": 0, "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="workers.generation_worker.warm_up_models")
def warm_up_models() -> Dict[str, Any]:
    logger.info("Warming up generation pipelines")
    asyncio.run(_generation_service.ensure_initialized())
    status = _generation_service.model_manager.get_status_snapshot()
    logger.info("Model manager warmed up in %s mode", status.get("mode"))
    return status


@celery_app.task(name="workers.generation_worker.dispatch_generation_job")
def dispatch_generation_job(
    job_id: str, request_data: Dict[str, Any], priority_tag: str = "realtime"
) -> str:
    return submit_generation_job(job_id, request_data, priority_tag=priority_tag)


@celery_app.task(name="workers.generation_worker.replay_local_queue")
def replay_local_queue(max_items: int = 100) -> Dict[str, int]:
    """Réémet les tâches génération stockées localement."""

    return _drain_local_queue(max_items=max_items)
