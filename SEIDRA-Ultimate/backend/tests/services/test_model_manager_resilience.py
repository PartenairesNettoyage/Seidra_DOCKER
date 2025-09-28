import asyncio
import base64
import importlib
from pathlib import Path
import sys
import types
from typing import Any

import pytest

try:  # pragma: no cover - compatibilité sans httpx installé
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    class _DummyRequest:
        def __init__(self, method: str, url: str) -> None:
            self.method = method
            self.url = url

    class _DummyResponse:
        def __init__(self, status_code: int, request: _DummyRequest) -> None:
            self.status_code = status_code
            self.request = request

    class HTTPStatusError(Exception):
        def __init__(self, message: str, request: _DummyRequest, response: _DummyResponse) -> None:
            super().__init__(message)
            self.request = request
            self.response = response

    class _HttpxFallback:
        Request = _DummyRequest

        class Response(_DummyResponse):
            def __init__(self, status_code: int, request: _DummyRequest) -> None:
                super().__init__(status_code, request)

        class Timeout:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        class Limits:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        class AsyncClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

        HTTPStatusError = HTTPStatusError

    httpx = _HttpxFallback()  # type: ignore


def _ensure_pydantic_stack() -> None:
    if "pydantic" not in sys.modules:
        module = types.ModuleType("pydantic")

        class _BaseModel:
            def __init__(self, **data: Any) -> None:
                for key, value in data.items():
                    setattr(self, key, value)

        def _field(default=None, *, default_factory=None, **_kwargs):  # noqa: ANN001
            if default_factory is not None:
                return default_factory()
            return default

        def _validator(*_args, **_kwargs):  # noqa: ANN001
            def decorator(func):
                return func

            return decorator

        module.BaseModel = _BaseModel
        module.Field = _field
        module.validator = _validator
        sys.modules["pydantic"] = module

    if "pydantic_settings" not in sys.modules:
        module = types.ModuleType("pydantic_settings")

        class _BaseSettings(sys.modules["pydantic"].BaseModel):  # type: ignore[attr-defined]
            model_config = {"extra": "allow"}

        module.BaseSettings = _BaseSettings
        sys.modules["pydantic_settings"] = module


def _ensure_httpx_stub() -> None:
    if "httpx" in sys.modules:
        return

    module = types.ModuleType("httpx")

    class AsyncClient:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class Timeout:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

    class Limits:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

    module.AsyncClient = AsyncClient
    module.Timeout = Timeout
    module.Limits = Limits
    sys.modules["httpx"] = module


def _ensure_pil_stub() -> None:
    if "PIL" in sys.modules and "PIL.Image" in sys.modules:
        return

    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")

    class _Image:
        pass

    def _new(*_args, **_kwargs) -> _Image:  # noqa: ANN001
        return _Image()

    image_module.Image = _Image
    image_module.new = _new
    pil_module.Image = image_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module


class StubNotificationService:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def push(
        self,
        level: str,
        title: str,
        message: str,
        *,
        category: str = "",
        metadata: dict[str, Any],
        tags: list[str],
    ) -> dict[str, Any]:
        entry = {
            "level": level,
            "title": title,
            "message": message,
            "category": category,
            "metadata": metadata,
            "tags": tags,
        }
        self.events.append(entry)
        return entry


class StubTelemetryService:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record_remote_call(
        self,
        service: str,
        endpoint: str,
        *,
        duration: float,
        success: bool,
        attempts: int,
        queue_length: int = 0,
    ) -> None:
        self.records.append(
            {
                "service": service,
                "endpoint": endpoint,
                "duration": duration,
                "success": success,
                "attempts": attempts,
                "queue_length": queue_length,
            }
        )


def _configure_settings(tmp_path: Path) -> None:
    _ensure_pydantic_stack()
    _ensure_httpx_stub()
    _ensure_pil_stub()

    from core import config

    importlib.reload(config)
    config.get_settings.cache_clear()

    comfy = config.RemoteServiceSettings(
        request_timeout_seconds=0.5,
        connect_timeout_seconds=0.1,
        read_timeout_seconds=0.1,
        write_timeout_seconds=0.1,
        max_attempts=1,
        backoff_factor=0.0,
        backoff_max_seconds=0.1,
        queue_max_retries=2,
        queue_retry_delay_seconds=0.0,
    )
    sadtalker = config.RemoteServiceSettings(
        request_timeout_seconds=0.5,
        connect_timeout_seconds=0.1,
        read_timeout_seconds=0.1,
        write_timeout_seconds=0.1,
        max_attempts=1,
        backoff_factor=0.0,
        backoff_max_seconds=0.1,
        queue_max_retries=1,
        queue_retry_delay_seconds=0.0,
    )

    config.settings = config.Settings(
        media_dir=tmp_path / "media",
        thumbnail_dir=tmp_path / "thumbnails",
        models_dir=tmp_path / "models",
        temp_dir=tmp_path / "tmp",
        comfyui_url="http://comfy.test",
        sadtalker_url="http://sadtalker.test",
        remote_inference=config.RemoteInferenceSettings(
            comfyui=comfy,
            sadtalker=sadtalker,
        ),
    )


def test_timeout_triggers_queue(monkeypatch, tmp_path) -> None:
    asyncio.run(_run_timeout_triggers_queue(monkeypatch, tmp_path))


async def _run_timeout_triggers_queue(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SEIDRA_USE_REAL_MODELS", "0")
    _configure_settings(tmp_path)

    from services import model_manager as model_manager_module

    importlib.reload(model_manager_module)
    manager = model_manager_module.ModelManager()
    telemetry = StubTelemetryService()
    notifications = StubNotificationService()
    manager.attach_telemetry_service(telemetry)
    manager.attach_notification_service(notifications)

    async def _noop_worker() -> None:
        return None

    monkeypatch.setattr(manager, "_ensure_retry_worker", _noop_worker)

    async def _failing_request(*_args: Any, **_kwargs: Any):  # noqa: ANN401
        raise TimeoutError()

    monkeypatch.setattr(manager, "_request_json_with_retries", _failing_request)

    with pytest.raises(TimeoutError):
        await manager._generate_image_remote(
            prompt="test",
            negative_prompt="",
            width=64,
            height=64,
            num_inference_steps=4,
            guidance_scale=7.5,
            lora_models=None,
            lora_weights=None,
            model_name="sdxl-base",
            media_dir=tmp_path / "media",
        )

    assert manager._remote_retry_queue.qsize() == 1
    assert notifications.events, "Une notification de dégradation doit être publiée"
    assert telemetry.records and telemetry.records[-1]["success"] is False

    queued_job = await manager._remote_retry_queue.get()
    manager._remote_retry_queue.task_done()
    assert getattr(queued_job, "service", None) == "comfyui"
    await manager.cleanup()


def test_retry_worker_completes_job(monkeypatch, tmp_path) -> None:
    asyncio.run(_run_retry_worker_completes_job(monkeypatch, tmp_path))


async def _run_retry_worker_completes_job(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SEIDRA_USE_REAL_MODELS", "0")
    _configure_settings(tmp_path)

    from services import model_manager as model_manager_module

    importlib.reload(model_manager_module)
    manager = model_manager_module.ModelManager()
    telemetry = StubTelemetryService()
    notifications = StubNotificationService()
    manager.attach_telemetry_service(telemetry)
    manager.attach_notification_service(notifications)

    image_payload = base64.b64encode(b"stub-image").decode("ascii")
    call_state = {"count": 0}

    async def _flaky_request(*_args: Any, **_kwargs: Any):  # noqa: ANN401
        call_state["count"] += 1
        if call_state["count"] == 1:
            response = httpx.Response(502, request=httpx.Request("POST", "http://comfy.test/api/generate"))
            raise httpx.HTTPStatusError("boom", request=response.request, response=response)
        return (
            {
                "images": [
                    {
                        "data": image_payload,
                        "filename": "retry.png",
                    }
                ],
                "metadata": {"status": "ok"},
            },
            1,
        )

    monkeypatch.setattr(manager, "_request_json_with_retries", _flaky_request)

    with pytest.raises(httpx.HTTPStatusError):
        await manager._generate_image_remote(
            prompt="retry",
            negative_prompt="",
            width=64,
            height=64,
            num_inference_steps=4,
            guidance_scale=7.5,
            lora_models=None,
            lora_weights=None,
            model_name="sdxl-base",
            media_dir=tmp_path / "media",
        )

    await asyncio.wait_for(manager._remote_retry_queue.join(), timeout=1.0)

    media_file = tmp_path / "media" / "retry.png"
    assert media_file.exists(), "Le fichier généré doit être présent après reprise"

    levels = [event["level"] for event in notifications.events]
    assert "warning" in levels and "info" in levels

    assert len(telemetry.records) >= 2
    assert any(record["success"] for record in telemetry.records)

    await manager.cleanup()
