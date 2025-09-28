import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import sys
import types
from typing import Any

import pytest

alembic_module = types.ModuleType("alembic")
alembic_command = types.ModuleType("alembic.command")
alembic_config = types.ModuleType("alembic.config")


def _noop_upgrade(*_args: Any, **_kwargs: Any) -> None:
    return None


class _StubConfig:
    def __init__(self, _path: str) -> None:
        self._path = _path

    def set_main_option(self, *_args: Any, **_kwargs: Any) -> None:
        return None


alembic_command.upgrade = _noop_upgrade
alembic_module.command = alembic_command
alembic_config.Config = _StubConfig

sys.modules.setdefault("alembic", alembic_module)
sys.modules.setdefault("alembic.command", alembic_command)
sys.modules.setdefault("alembic.config", alembic_config)


class _StubSettings:
    def __init__(self) -> None:
        base_dir = Path("/tmp/seidra-tests")
        (base_dir / "models").mkdir(parents=True, exist_ok=True)
        (base_dir / "media").mkdir(parents=True, exist_ok=True)
        self.models_directory = base_dir / "models"
        self.media_directory = base_dir / "media"
        self.celery_broker_url = "redis://localhost:6379/0"
        self.redis_url = "redis://localhost:6379/0"
        self.celery_result_backend = "redis://localhost:6379/0"


core_config_stub = types.ModuleType("core.config")
core_config_stub.settings = _StubSettings()

sys.modules.setdefault("core.config", core_config_stub)


pil_module = types.ModuleType("PIL")
pil_image_module = types.ModuleType("PIL.Image")
pil_draw_module = types.ModuleType("PIL.ImageDraw")
pil_font_module = types.ModuleType("PIL.ImageFont")


class _StubImage:
    def __init__(self, mode: str = "RGB", size: Any = (1, 1), color: Any = None) -> None:
        self.mode = mode
        self.size = size
        self.color = color

    def save(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _image_new(mode: str, size: Any, color: Any = None) -> _StubImage:
    return _StubImage(mode=mode, size=size, color=color)


class _StubDraw:
    def __init__(self, _image: _StubImage) -> None:
        self._image = _image

    def text(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class _StubFont:
    @staticmethod
    def truetype(*_args: Any, **_kwargs: Any) -> None:
        return None


pil_image_module.new = _image_new
pil_image_module.Image = types.SimpleNamespace(new=_image_new)
pil_draw_module.Draw = _StubDraw
pil_font_module.truetype = _StubFont.truetype

pil_module.Image = pil_image_module
pil_module.ImageDraw = pil_draw_module
pil_module.ImageFont = pil_font_module

sys.modules.setdefault("PIL", pil_module)
sys.modules.setdefault("PIL.Image", pil_image_module)
sys.modules.setdefault("PIL.ImageDraw", pil_draw_module)
sys.modules.setdefault("PIL.ImageFont", pil_font_module)


httpx_stub = types.ModuleType("httpx")


class _StubAsyncStream:
    async def __aenter__(self) -> "_StubAsyncStream":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def aiter_bytes(self):  # pragma: no cover - unused in tests
        if False:
            yield b""


class _StubResponse:
    def __init__(self) -> None:
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {}


class _StubAsyncClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def __aenter__(self) -> "_StubAsyncClient":
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def stream(self, *_args: Any, **_kwargs: Any) -> _StubAsyncStream:
        return _StubAsyncStream()

    async def get(self, *_args: Any, **_kwargs: Any) -> _StubResponse:
        return _StubResponse()


httpx_stub.AsyncClient = _StubAsyncClient
httpx_stub.TimeoutException = RuntimeError
httpx_stub.RequestError = RuntimeError
httpx_stub.HTTPStatusError = RuntimeError

sys.modules.setdefault("httpx", httpx_stub)


psutil_stub = types.ModuleType("psutil")
psutil_stub.cpu_percent = lambda *_args, **_kwargs: 0.0
psutil_stub.virtual_memory = lambda: types.SimpleNamespace(total=0, available=0, percent=0.0)
psutil_stub.sensors_temperatures = lambda: {}


class _StubProcess:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def as_dict(self) -> dict[str, Any]:
        return {}


psutil_stub.Process = _StubProcess

sys.modules.setdefault("psutil", psutil_stub)


fastapi_stub = types.ModuleType("fastapi")


class _StubWebSocket:
    async def accept(self) -> None:
        return None

    async def send_text(self, *_args: Any, **_kwargs: Any) -> None:
        return None


fastapi_stub.WebSocket = _StubWebSocket

sys.modules.setdefault("fastapi", fastapi_stub)


database_stub = types.ModuleType("services.database")


@dataclass
class _Job:
    id: str
    user_id: int
    persona_id: int | None
    job_type: str
    prompt: str
    negative_prompt: str
    model_name: str
    lora_models: list[str]
    parameters: dict[str, Any]
    status: str
    metadata_payload: dict[str, Any]
    is_nsfw: bool
    progress: float = 0.0
    error_message: str | None = None
    result_images: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class DatabaseService:
    _jobs: dict[str, _Job] = {}
    _media: list[dict[str, Any]] = []

    def __init__(self) -> None:
        return None

    def create_job(self, **kwargs: Any) -> _Job:
        metadata = dict(kwargs.pop("metadata", {}))
        job = _Job(metadata_payload=metadata, **kwargs)
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> _Job | None:
        return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs: Any) -> _Job | None:
        job = self._jobs.get(job_id)
        if not job:
            return None
        if "metadata" in kwargs:
            kwargs["metadata_payload"] = kwargs.pop("metadata")
        for key, value in kwargs.items():
            setattr(job, key, value)
        job.updated_at = datetime.utcnow()
        self._jobs[job_id] = job
        return job

    def create_media_item(self, **kwargs: Any) -> dict[str, Any]:
        self._media.append(kwargs)
        return kwargs

    def close(self) -> None:
        return None


database_stub.DatabaseService = DatabaseService  # type: ignore[attr-defined]

sys.modules.setdefault("services.database", database_stub)

from services.database import DatabaseService  # type: ignore  # noqa: E402
from services.generation_service import GenerationService, GPUUnavailableError  # noqa: E402


class SlowModelManager:
    """Model manager stub that simulates a GPU-driven pipeline."""

    def __init__(self) -> None:
        self.use_mock_pipeline = False
        self.status: dict[str, Any] = {
            "initialized": False,
            "mode": "cuda",
            "health": "healthy",
            "last_error": None,
        }

    async def initialize(self) -> None:
        self.status["initialized"] = True

    def get_status_snapshot(self) -> dict[str, Any]:
        return dict(self.status)

    def mark_unavailable(self, reason: str) -> None:
        self.status.update(mode="degraded", health="degraded", last_error=reason)

    def mark_available(self) -> None:
        self.status.update(mode="cuda", health="healthy", last_error=None)

    async def generate_image(self, *args: Any, **_kwargs: Any) -> list[str]:
        await asyncio.sleep(0.05)
        return []

    def get_last_generation_metrics(self, reset: bool = False) -> dict[str, Any]:
        return {}


class StatusAwareModelManager(SlowModelManager):
    def __init__(self) -> None:
        super().__init__()
        self.generate_calls = 0

    async def generate_image(self, *args: Any, **kwargs: Any) -> list[str]:
        self.generate_calls += 1
        return await super().generate_image(*args, **kwargs)


@dataclass
class StubNotificationService:
    messages: list[dict[str, Any]]

    async def push(
        self,
        level: str,
        title: str,
        message: str,
        *,
        category: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "level": level,
            "title": title,
            "message": message,
            "category": category,
            "metadata": metadata or {},
        }
        self.messages.append(entry)
        return entry


class StubWebSocketManager:
    def __init__(self) -> None:
        self.progress_events: list[dict[str, Any]] = []
        self.completion_events: list[dict[str, Any]] = []

    async def send_generation_progress(
        self,
        job_id: str,
        progress: float,
        user_id: int,
        status: str,
        message: str,
        metadata: dict[str, Any],
    ) -> None:
        self.progress_events.append(
            {
                "job_id": job_id,
                "progress": progress,
                "user_id": user_id,
                "status": status,
                "message": message,
                "metadata": metadata,
            }
        )

    async def send_generation_complete(
        self,
        job_id: str,
        _results: list[str],
        user_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.completion_events.append(
            {
                "job_id": job_id,
                "user_id": user_id,
                "metadata": metadata or {},
            }
        )

    async def send_generation_error(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        return None

    async def dispatch_event(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        return None


def test_gpu_timeout_triggers_degraded_mode() -> None:
    async def _run() -> None:
        db = DatabaseService()
        job_id = "job-timeout"
        try:
            db.create_job(
                id=job_id,
                user_id=1,
                persona_id=None,
                job_type="image",
                prompt="A cyberpunk city",
                negative_prompt="",
                model_name="sdxl-base",
                lora_models=[],
                parameters={"width": 512, "height": 512},
                status="pending",
                metadata={},
                is_nsfw=False,
            )

            model_manager = SlowModelManager()
            websocket_manager = StubWebSocketManager()
            notification_service = StubNotificationService(messages=[])
            service = GenerationService(
                model_manager=model_manager,
                websocket_manager=websocket_manager,
                notification_service=notification_service,
            )
            service.GPU_TIMEOUT_SECONDS = 0.01
            service.DEGRADED_BACKOFF_SECONDS = 1

            with pytest.raises(GPUUnavailableError):
                await service.process_job(job_id, {"prompt": "A cyberpunk city"}, priority_tag="realtime")

            job = db.get_job(job_id)
            assert job is not None
            assert job.status == "pending"
            assert job.error_message == "GPU inference timeout"
            degraded_meta = job.metadata_payload.get("degraded", {}) if job.metadata_payload else {}
            assert degraded_meta.get("retry_after_seconds") == service.DEGRADED_BACKOFF_SECONDS
            assert degraded_meta.get("priority") == "realtime"

            assert websocket_manager.progress_events, "Progress event should be emitted"
            delayed_event = websocket_manager.progress_events[-1]
            assert delayed_event["status"] == "delayed"
            assert "retryAfter" in delayed_event["metadata"]

            assert notification_service.messages, "User notification should be emitted"
            assert notification_service.messages[0]["level"] == "warning"

            status_snapshot = model_manager.get_status_snapshot()
            assert status_snapshot["mode"] == "degraded"
            assert status_snapshot["health"] == "degraded"
        finally:
            db.close()

    asyncio.run(_run())


def test_priority_queue_requeues_after_gpu_unavailability() -> None:
    async def _run() -> None:
        db = DatabaseService()
        job_id = "job-queue"
        service: GenerationService | None = None
        try:
            db.create_job(
                id=job_id,
                user_id=1,
                persona_id=None,
                job_type="image",
                prompt="Queue test",
                negative_prompt="",
                model_name="sdxl-base",
                lora_models=[],
                parameters={"width": 512, "height": 512},
                status="pending",
                metadata={},
                is_nsfw=False,
            )

            model_manager = SlowModelManager()
            websocket_manager = StubWebSocketManager()
            service = GenerationService(
                model_manager=model_manager,
                websocket_manager=websocket_manager,
                notification_service=None,
            )
            service.GPU_TIMEOUT_SECONDS = 0.01
            service.DEGRADED_BACKOFF_SECONDS = 0.05

            await service.enqueue_job(job_id, {"prompt": "Queue test"}, priority_tag="realtime")

            await asyncio.sleep(0.1)

            job = db.get_job(job_id)
            assert job is not None
            degraded_meta = job.metadata_payload.get("degraded", {}) if job.metadata_payload else {}
            assert degraded_meta.get("priority") == "realtime"
            assert service._current_degraded_reason() is not None
        finally:
            if service and service._queue_worker_task:
                service._queue_worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await service._queue_worker_task
            db.close()

    asyncio.run(_run())


def test_realtime_jobs_take_precedence_over_batch_queue() -> None:
    async def _run() -> None:
        db = DatabaseService()
        db._jobs.clear()
        realtime_job_id = "job-realtime"
        batch_job_id = "job-batch"
        service: GenerationService | None = None
        try:
            db.create_job(
                id=batch_job_id,
                user_id=1,
                persona_id=None,
                job_type="image",
                prompt="Batch first",
                negative_prompt="",
                model_name="sdxl-base",
                lora_models=[],
                parameters={"width": 512, "height": 512},
                status="pending",
                metadata={},
                is_nsfw=False,
            )
            db.create_job(
                id=realtime_job_id,
                user_id=1,
                persona_id=None,
                job_type="image",
                prompt="Realtime second",
                negative_prompt="",
                model_name="sdxl-base",
                lora_models=[],
                parameters={"width": 512, "height": 512},
                status="pending",
                metadata={},
                is_nsfw=False,
            )

            model_manager = SlowModelManager()
            websocket_manager = StubWebSocketManager()
            service = GenerationService(
                model_manager=model_manager,
                websocket_manager=websocket_manager,
                notification_service=None,
            )

            await service.enqueue_job(
                batch_job_id,
                {"prompt": "Batch first"},
                priority_tag="batch",
                delay_seconds=0.05,
            )
            await service.enqueue_job(
                realtime_job_id,
                {"prompt": "Realtime second"},
                priority_tag="realtime",
            )

            async def _wait_for(job_id: str) -> _Job:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 1.0
                while loop.time() < deadline:
                    job = db.get_job(job_id)
                    if job and job.status == "completed":
                        return job
                    await asyncio.sleep(0.05)
                job = db.get_job(job_id)
                assert job is not None
                return job

            realtime_job = await _wait_for(realtime_job_id)
            assert websocket_manager.completion_events, "jobs should complete"
            first_completed = websocket_manager.completion_events[0]
            assert first_completed["job_id"] == realtime_job_id

            batch_job = await _wait_for(batch_job_id)
            assert realtime_job is not None and batch_job is not None
            assert realtime_job.status == "completed"
            assert batch_job.status == "completed"
            assert realtime_job.completed_at is not None
            assert batch_job.completed_at is not None
            assert realtime_job.completed_at <= batch_job.completed_at
        finally:
            if service and service._queue_worker_task:
                service._queue_worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await service._queue_worker_task
            db.close()

    asyncio.run(_run())


def test_model_manager_degraded_status_triggers_fallback() -> None:
    async def _run() -> None:
        db = DatabaseService()
        job_id = "job-status"
        try:
            db.create_job(
                id=job_id,
                user_id=1,
                persona_id=None,
                job_type="image",
                prompt="Status fallback",
                negative_prompt="",
                model_name="sdxl-base",
                lora_models=[],
                parameters={"width": 512, "height": 512},
                status="pending",
                metadata={},
                is_nsfw=False,
            )

            model_manager = StatusAwareModelManager()
            model_manager.status.update(
                mode="maintenance",
                health="unhealthy",
                available=False,
                last_error="GPU maintenance window",
            )
            websocket_manager = StubWebSocketManager()
            notification_service = StubNotificationService(messages=[])
            service = GenerationService(
                model_manager=model_manager,
                websocket_manager=websocket_manager,
                notification_service=notification_service,
            )
            service.DEGRADED_BACKOFF_SECONDS = 1

            with pytest.raises(GPUUnavailableError):
                await service.process_job(job_id, {"prompt": "Status fallback"}, priority_tag="batch")

            job = db.get_job(job_id)
            assert job is not None
            assert job.status == "pending"
            degraded_meta = job.metadata_payload.get("degraded", {}) if job.metadata_payload else {}
            assert degraded_meta.get("priority") == "batch"
            history = degraded_meta.get("history", [])
            assert history, "degraded metadata should include history"
            assert history[-1]["reason"] == "GPU maintenance window"

            assert websocket_manager.progress_events, "Progress event should be emitted"
            assert websocket_manager.progress_events[-1]["status"] == "delayed"

            assert notification_service.messages, "Notification should be sent"
            assert notification_service.messages[-1]["level"] == "warning"

            assert service._current_degraded_reason() == "GPU maintenance window"
            assert model_manager.generate_calls == 0
        finally:
            db.close()

    asyncio.run(_run())
