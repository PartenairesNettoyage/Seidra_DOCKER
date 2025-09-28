"""Central Celery application used by SEIDRA Ultimate workers."""

from __future__ import annotations

from datetime import timedelta

from celery import Celery
from celery.schedules import crontab
from kombu import Queue

from core.config import settings


BROKER_URL = settings.celery_broker_url or settings.redis_url
RESULT_BACKEND = settings.celery_result_backend or settings.redis_url


celery_app = Celery(
    "seidra_workers",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "workers.generation_worker",
        "workers.model_worker",
        "workers.media_worker",
        "workers.video_worker",
        "workers.recovery_worker",
    ],
)


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=10,
    task_routes={
        "workers.generation_worker.generate_images_task": {
            "queue": "generation.realtime",
            "routing_key": "generation.realtime",
        },
        "workers.generation_worker.batch_generate_images_task": {
            "queue": "generation.batch",
            "routing_key": "generation.batch",
        },
        "workers.generation_worker.dispatch_generation_job": {
            "queue": "generation.realtime",
            "routing_key": "generation.realtime",
        },
        "workers.generation_worker.cleanup_old_jobs": {
            "queue": "generation.batch",
        },
        "workers.generation_worker.warm_up_models": {
            "queue": "generation.realtime",
        },
        "workers.model_worker.*": {"queue": "models"},
        "workers.media_worker.*": {"queue": "media"},
        "workers.video_worker.*": {"queue": "video"},
        "workers.recovery_worker.*": {"queue": "recovery"},
    },
)


celery_app.conf.task_default_queue = "generation.realtime"
celery_app.conf.task_queues = (
    Queue(
        "generation.realtime",
        routing_key="generation.realtime",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "generation.batch",
        routing_key="generation.batch",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue("models"),
    Queue("media"),
    Queue("video"),
    Queue("recovery"),
)
celery_app.conf.task_default_priority = 5
celery_app.conf.task_queue_max_priority = 9
celery_app.conf.worker_disable_rate_limits = True
celery_app.conf.broker_connection_retry_on_startup = True


celery_app.conf.beat_schedule = {
    "cleanup-old-jobs": {
        "task": "workers.generation_worker.cleanup_old_jobs",
        "schedule": crontab(hour=2, minute=0),
    },
    "warm-up-models": {
        "task": "workers.generation_worker.warm_up_models",
        "schedule": crontab(minute="*/30"),
    },
    "drain-generation-local-queue": {
        "task": "workers.generation_worker.replay_local_queue",
        "schedule": timedelta(minutes=1),
    },
    "sync-media-library": {
        "task": "workers.media_worker.sync_media_library",
        "schedule": crontab(minute=15, hour="*/6"),
    },
    "resume-stuck-jobs": {
        "task": "workers.recovery_worker.resume_stuck_jobs",
        "schedule": timedelta(minutes=5),
    },
    "retry-failed-jobs": {
        "task": "workers.recovery_worker.retry_failed_jobs",
        "schedule": crontab(minute="*/30"),
    },
    "refresh-model-catalog": {
        "task": "workers.model_worker.refresh_model_catalog",
        "schedule": crontab(minute=0, hour="*/4"),
    },
}


if __name__ == "__main__":
    celery_app.start()
