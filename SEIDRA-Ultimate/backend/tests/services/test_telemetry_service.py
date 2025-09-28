import asyncio
from datetime import datetime, timedelta
import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

if "alembic" not in sys.modules:
    alembic_module = types.ModuleType("alembic")
    alembic_module.command = types.SimpleNamespace(upgrade=lambda *args, **kwargs: None)
    sys.modules["alembic"] = alembic_module
    config_module = types.ModuleType("alembic.config")

    class _DummyConfig:  # pragma: no cover - simple stub
        def __init__(self, *args, **kwargs) -> None:
            pass

        def set_main_option(self, *args, **kwargs) -> None:
            pass

    config_module.Config = _DummyConfig
    sys.modules["alembic.config"] = config_module


if "services.database" not in sys.modules:
    database_module = types.ModuleType("services.database")

    class _PlaceholderDatabaseService:  # pragma: no cover - simple stub
        def __init__(self, *args, **kwargs) -> None:
            pass

        def close(self) -> None:
            pass

        def get_platform_summary(self) -> dict[str, Any]:
            return {}

        def get_job_statistics(self) -> dict[str, Any]:
            return {}

        def get_media_statistics(self) -> dict[str, Any]:
            return {}

        def aggregate_generation_metrics(self, **kwargs: Any) -> dict[str, Any]:
            return {"total": 0, "outputs": 0}

    database_module.DatabaseService = _PlaceholderDatabaseService
    sys.modules["services.database"] = database_module


if "psutil" not in sys.modules:
    psutil_module = types.ModuleType("psutil")

    def _cpu_percent(interval=None):  # pragma: no cover - stub
        return 0.0

    class _VirtualMemory:  # pragma: no cover - stub structure
        percent = 0.0
        total = 0
        available = 0

    def _virtual_memory():
        return _VirtualMemory()

    def _boot_time():
        return 0

    psutil_module.cpu_percent = _cpu_percent
    psutil_module.virtual_memory = _virtual_memory
    psutil_module.boot_time = _boot_time
    sys.modules["psutil"] = psutil_module


if "httpx" not in sys.modules:
    httpx_module = types.ModuleType("httpx")

    class _AsyncClient:  # pragma: no cover - stub client
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError("httpx stub: GET not implemented")

        async def stream(self, *args, **kwargs):
            raise RuntimeError("httpx stub: stream not implemented")

    httpx_module.AsyncClient = _AsyncClient
    httpx_module.Response = object
    sys.modules["httpx"] = httpx_module


if "PIL" not in sys.modules:
    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")

    class _DummyImage:  # pragma: no cover - stub
        @staticmethod
        def open(*args, **kwargs):
            raise RuntimeError("Pillow stub: open not implemented")

    image_module.Image = _DummyImage
    pil_module.Image = _DummyImage
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module


sys.modules.pop("core.config", None)
sys.modules.pop("fastapi", None)


from services.telemetry_service import TelemetryService  # noqa: E402


class DummyDatabaseService:
    records: list[SimpleNamespace] = []

    def __init__(self) -> None:
        self._now = datetime.utcnow()

    def get_platform_summary(self) -> dict[str, Any]:
        return {"uptimeSeconds": 1234}

    def get_job_statistics(self) -> dict[str, Any]:
        return {"running": 0, "completed": 0}

    def get_media_statistics(self) -> dict[str, Any]:
        return {"items": 0}

    def close(self) -> None:  # pragma: no cover - compatibility
        pass

    def create_generation_metric(self, **kwargs: Any) -> SimpleNamespace:
        record = SimpleNamespace(
            id=len(DummyDatabaseService.records) + 1,
            created_at=self._now,
            **kwargs,
        )
        DummyDatabaseService.records.append(record)
        return record

    def serialize_generation_metric(self, record: SimpleNamespace) -> dict[str, Any]:
        return {
            "id": record.id,
            "jobId": record.job_id,
            "userId": record.user_id,
            "personaId": record.persona_id,
            "mediaType": record.media_type,
            "modelName": record.model_name,
            "prompt": record.prompt,
            "outputs": record.outputs,
            "durationSeconds": record.duration_seconds,
            "throughput": record.throughput,
            "vramAllocatedMb": record.vram_allocated_mb,
            "vramReservedMb": record.vram_reserved_mb,
            "vramPeakMb": record.vram_peak_mb,
            "vramDeltaMb": record.vram_delta_mb,
            "extra": record.extra,
            "createdAt": record.created_at.isoformat(),
        }

    def list_generation_metrics(
        self,
        *,
        limit: int = 50,
        since_minutes: int | None = None,
        media_type: str | None = None,
    ) -> list[SimpleNamespace]:
        items = list(DummyDatabaseService.records)
        if since_minutes is not None:
            threshold = self._now - timedelta(minutes=since_minutes)
            items = [item for item in items if item.created_at >= threshold]
        if media_type is not None:
            items = [item for item in items if item.media_type == media_type]
        return list(reversed(items[:limit]))

    def aggregate_generation_metrics(
        self,
        *,
        since_minutes: int | None = None,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        items = self.list_generation_metrics(limit=len(DummyDatabaseService.records), since_minutes=since_minutes, media_type=media_type)
        durations = [item.duration_seconds for item in items if item.duration_seconds is not None]
        throughput = [item.throughput for item in items if item.throughput is not None]
        vram_peaks = [item.vram_peak_mb for item in items if item.vram_peak_mb is not None]
        vram_deltas = [item.vram_delta_mb for item in items if item.vram_delta_mb is not None]
        outputs = [item.outputs for item in items if item.outputs is not None]
        return {
            "total": len(items),
            "averageDurationSeconds": sum(durations) / len(durations) if durations else None,
            "averageThroughput": sum(throughput) / len(throughput) if throughput else None,
            "averagePeakVramMb": sum(vram_peaks) / len(vram_peaks) if vram_peaks else None,
            "averageDeltaVramMb": sum(vram_deltas) / len(vram_deltas) if vram_deltas else None,
            "outputs": sum(outputs) if outputs else 0,
        }


class DummyGPU:
    def __init__(self) -> None:
        self.current_status = {
            "gpu_available": True,
            "temperature": 62.0,
            "utilization": 48.0,
            "memory_used": 4096,
            "memory_total": 24576,
            "memory_free": 20480,
            "memory_max_allocated": 6144,
            "inference_avg_seconds": None,
            "inference_samples": 0,
            "cuda_error_count": 0,
            "cuda_errors": [],
        }
        self._durations: list[float] = []

    async def get_status(self) -> dict[str, Any]:
        return dict(self.current_status)

    async def get_performance_metrics(self) -> dict[str, Any]:
        return {"status": "optimal"}

    def record_generation_metrics(
        self,
        *,
        duration: float | None = None,
        throughput: float | None = None,
        vram_delta: float | None = None,
        vram_peak: float | None = None,
    ) -> None:
        if duration is not None:
            self._durations.append(duration)
            avg = sum(self._durations) / len(self._durations)
            self.current_status["inference_avg_seconds"] = avg
            self.current_status["inference_samples"] = len(self._durations)
        if vram_peak is not None:
            self.current_status["last_generation_vram_peak_mb"] = vram_peak
        if vram_delta is not None:
            self.current_status["last_generation_vram_delta_mb"] = vram_delta

    def get_average_inference_time(self) -> float | None:
        if not self._durations:
            return None
        return sum(self._durations) / len(self._durations)

    def get_cuda_error_stats(self) -> dict[str, Any]:
        return {
            "count": len(self.current_status["cuda_errors"]),
            "recent": list(self.current_status["cuda_errors"]),
        }


class DummyWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def dispatch_event(self, message: dict[str, Any], *, channels=None, user_id=None) -> None:  # type: ignore[override]
        self.messages.append(message)


@pytest.fixture(autouse=True)
def patch_database(monkeypatch: pytest.MonkeyPatch):
    from services import telemetry_service as telemetry_module

    DummyDatabaseService.records.clear()
    monkeypatch.setattr(telemetry_module, "DatabaseService", DummyDatabaseService)
    yield
    DummyDatabaseService.records.clear()


def test_record_generation_metric_enriches_recent_metrics():
    gpu = DummyGPU()
    websocket = DummyWebSocket()
    service = TelemetryService(gpu_monitor=gpu, websocket_manager=websocket)

    metric_payload = {
        "job_id": "job-1",
        "user_id": 1,
        "persona_id": None,
        "media_type": "image",
        "model_name": "my-model",
        "prompt": "test",
        "outputs": 2,
        "duration_seconds": 1.5,
        "throughput": 1.33,
        "vram_allocated_mb": 5120,
        "vram_reserved_mb": 6144,
        "vram_peak_mb": 8192,
        "vram_delta_mb": 256,
        "extra": {},
    }

    enriched = asyncio.run(service.record_generation_metric(metric_payload))

    assert enriched["latencySeconds"] == pytest.approx(1.5)
    assert enriched["vramDeltaMB"] == pytest.approx(256)
    assert enriched["throughput"] == pytest.approx(1.33)
    assert enriched.get("rollingLatencySeconds") == pytest.approx(1.5)
    assert enriched["cudaErrors"]["count"] == 0
    assert service._recent_generation_metrics[0] == enriched
    assert websocket.messages and websocket.messages[0]["payload"] == enriched


def test_collect_snapshot_includes_gpu_and_generation_metrics():
    gpu = DummyGPU()
    service = TelemetryService(gpu_monitor=gpu)

    asyncio.run(
        service.record_generation_metric(
        {
            "job_id": "job-2",
            "user_id": 2,
            "persona_id": None,
            "media_type": "image",
            "model_name": "my-model",
            "prompt": "test",
            "outputs": 1,
            "duration_seconds": 2.0,
            "throughput": 0.5,
            "vram_allocated_mb": 4096,
            "vram_reserved_mb": 5120,
            "vram_peak_mb": 7168,
            "vram_delta_mb": 512,
            "extra": {},
        }
        )
    )

    snapshot = asyncio.run(service.collect_snapshot())

    assert snapshot["gpu"]["memory_max_allocated"] == 6144
    assert snapshot["gpu"]["inference_avg_seconds"] == pytest.approx(2.0)
    assert snapshot["generation"]["recent"]
    latest_generation = snapshot["generation"]["recent"][0]
    assert latest_generation["latencySeconds"] == pytest.approx(2.0)
    assert snapshot["generation"]["rollingLatencySeconds"] == pytest.approx(2.0)
