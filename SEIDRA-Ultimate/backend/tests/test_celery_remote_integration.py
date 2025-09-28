import base64
import json as jsonlib
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse
import uuid

import pytest


def _ensure_httpx_stub() -> None:
    try:
        import httpx  # type: ignore  # noqa: F401
        return
    except ModuleNotFoundError:  # pragma: no cover - executed in lightweight CI containers
        pass

    class URL:
        def __init__(self, value: str):
            parsed = urlparse(value)
            self.scheme = parsed.scheme
            self.host = parsed.hostname or ""
            self.port = parsed.port
            self.path = parsed.path or "/"
            self.query = parsed.query
            self._raw = value

        def __str__(self) -> str:  # pragma: no cover - debug helper
            return self._raw

    class Request:
        def __init__(self, method: str, url: str, *, json_data: Any | None = None):
            self.method = method.upper()
            self.url = URL(url)
            self.headers: dict[str, str] = {}
            self._json = json_data

        @property
        def content(self) -> bytes:
            if self._json is None:
                return b""
            return jsonlib.dumps(self._json).encode("utf-8")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message: str, request: "Request", response: "Response") -> None:
            super().__init__(message)
            self.request = request
            self.response = response

    class Response:
        def __init__(
            self,
            status_code: int,
            *,
            json: Any | None = None,
            content: bytes | None = None,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.status_code = status_code
            if content is None and json is not None:
                content = jsonlib.dumps(json).encode("utf-8")
            self._content = content or b""
            self._json = json
            self.headers = headers or {}

        async def __aenter__(self) -> "Response":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise HTTPStatusError("Request failed", getattr(self, "request", None), self)

        def json(self) -> Any:
            if self._json is not None:
                return self._json
            return jsonlib.loads(self._content.decode("utf-8"))

        async def aiter_bytes(self):
            yield self._content

        @property
        def content(self) -> bytes:
            return self._content

    class Timeout:
        def __init__(self, *_, **__):
            pass

    class MockTransport:
        def __init__(self, handler):
            self.handler = handler

    class AsyncClient:
        def __init__(self, *, transport: MockTransport | None = None, timeout: Timeout | None = None):
            self._transport = transport
            self._timeout = timeout

        async def __aenter__(self) -> "AsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            await self.aclose()

        async def aclose(self) -> None:
            return None

        async def post(self, url: str, json: Any | None = None) -> Response:
            return await self._send("POST", url, json)

        async def get(self, url: str) -> Response:
            return await self._send("GET", url, None)

        def stream(self, method: str, url: str):
            request = Request(method, url)
            response = self._call_handler(request)
            response.request = request  # type: ignore[attr-defined]
            return _ResponseContextManager(response)

        async def _send(self, method: str, url: str, json_payload: Any | None) -> Response:
            request = Request(method, url, json_data=json_payload)
            response = self._call_handler(request)
            response.request = request  # type: ignore[attr-defined]
            response.raise_for_status()
            return response

        def _call_handler(self, request: Request) -> Response:
            if not self._transport:
                raise RuntimeError("Mock httpx client cannot perform real HTTP requests")
            response = self._transport.handler(request)
            if not isinstance(response, Response):
                raise TypeError("MockTransport handler must return Response")
            return response

    class _ResponseContextManager:
        def __init__(self, response: Response) -> None:
            self._response = response

        async def __aenter__(self) -> Response:
            return self._response

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    stub = type(sys)("httpx")
    stub.URL = URL
    stub.Request = Request
    stub.Response = Response
    stub.AsyncClient = AsyncClient
    stub.MockTransport = MockTransport
    stub.Timeout = Timeout
    stub.HTTPError = HTTPError
    stub.HTTPStatusError = HTTPStatusError
    sys.modules["httpx"] = stub


_ensure_httpx_stub()
import httpx  # type: ignore  # noqa: E402


def _ensure_pydantic_stack() -> None:
    if "pydantic" not in sys.modules:
        import types

        class _BaseModel:
            def __init__(self, **data: Any) -> None:
                for key, value in data.items():
                    setattr(self, key, value)

        def _field(default=None, *, env=None, default_factory=None, **_kwargs):  # noqa: ANN001
            if default_factory is not None:
                return default_factory()
            return default

        def _validator(*_args, **_kwargs):  # noqa: ANN001
            def decorator(func):
                return func

            return decorator

        pydantic_module = types.ModuleType("pydantic")
        pydantic_module.BaseModel = _BaseModel
        pydantic_module.Field = _field
        pydantic_module.validator = _validator
        sys.modules["pydantic"] = pydantic_module

    if "pydantic_settings" not in sys.modules:
        import types

        class _BaseSettings(sys.modules["pydantic"].BaseModel):  # type: ignore[attr-defined]
            model_config: dict[str, Any] = {"extra": "allow"}

        settings_module = types.ModuleType("pydantic_settings")
        settings_module.BaseSettings = _BaseSettings
        sys.modules["pydantic_settings"] = settings_module


def _ensure_alembic_stub() -> None:
    if "alembic" in sys.modules:
        return

    import types

    command_module = types.ModuleType("alembic.command")

    def _upgrade(*_args, **_kwargs) -> None:  # noqa: ANN001
        return None

    command_module.upgrade = _upgrade

    config_module = types.ModuleType("alembic.config")

    class _Config:
        def __init__(self, *_args, **_kwargs) -> None:  # noqa: ANN001
            self.options: dict[str, Any] = {}

        def set_main_option(self, key: str, value: str) -> None:
            self.options[key] = value

    config_module.Config = _Config

    alembic_module = types.ModuleType("alembic")
    alembic_module.command = command_module
    alembic_module.config = config_module
    sys.modules["alembic"] = alembic_module
    sys.modules["alembic.command"] = command_module
    sys.modules["alembic.config"] = config_module


def _install_database_stub() -> None:
    from datetime import datetime
    import types
    from types import SimpleNamespace

    if "services.database" in sys.modules:
        return

    storage: dict[str, Any] = {"users": {}, "jobs": {}, "media": []}

    class User(SimpleNamespace):
        pass

    class GenerationJob(SimpleNamespace):
        pass

    class MediaItem(SimpleNamespace):
        pass

    class DatabaseService:
        def __init__(self) -> None:
            self._storage = storage

        def close(self) -> None:  # pragma: no cover
            return None

        def create_user(self, username: str, email: str, hashed_password: str) -> User:
            user_id = len(self._storage["users"]) + 1
            user = User(id=user_id, username=username, email=email, hashed_password=hashed_password)
            self._storage["users"][user_id] = user
            return user

        def create_job(self, **kwargs: Any) -> GenerationJob:
            job_id = kwargs.get("id") or str(len(self._storage["jobs"]) + 1)
            job = GenerationJob(
                id=job_id,
                user_id=kwargs.get("user_id", 1),
                job_type=kwargs.get("job_type", "image"),
                prompt=kwargs.get("prompt", ""),
                negative_prompt=kwargs.get("negative_prompt", ""),
                model_name=kwargs.get("model_name", "sdxl-base"),
                lora_models=kwargs.get("lora_models", []),
                parameters=kwargs.get("parameters", {}),
                status=kwargs.get("status", "pending"),
                progress=kwargs.get("progress", 0.0),
                result_images=kwargs.get("result_images", []),
                metadata_payload=kwargs.get("metadata_payload", {}),
                created_at=kwargs.get("created_at", datetime.utcnow()),
                updated_at=kwargs.get("created_at", datetime.utcnow()),
                completed_at=kwargs.get("completed_at"),
            )
            self._storage["jobs"][job_id] = job
            return job

        def update_job(self, job_id: str, **kwargs: Any) -> GenerationJob | None:
            job = self._storage["jobs"].get(job_id)
            if not job:
                defaults = {
                    "id": job_id,
                    "user_id": kwargs.get("user_id", 1),
                    "job_type": kwargs.get("job_type", "image"),
                    "prompt": kwargs.get("prompt", ""),
                    "model_name": kwargs.get("model_name", "sdxl-base"),
                }
                job = self.create_job(**defaults)
            for key, value in kwargs.items():
                if key == "metadata":
                    key = "metadata_payload"
                setattr(job, key, value)
            job.updated_at = datetime.utcnow()
            return job

        def create_media_item(self, **kwargs: Any) -> MediaItem:
            media = MediaItem(**kwargs)
            self._storage["media"].append(media)
            return media

    stub_module = types.ModuleType("services.database")
    stub_module.DatabaseService = DatabaseService
    stub_module.GenerationJob = GenerationJob
    stub_module.MediaItem = MediaItem
    stub_module.User = User
    stub_module.__spec__ = SimpleNamespace(name="services.database")
    sys.modules["services.database"] = stub_module


def _install_pil_stub() -> None:
    import types

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


def _install_fastapi_stub() -> None:
    import types

    if "fastapi" in sys.modules:
        return

    fastapi_module = types.ModuleType("fastapi")

    class WebSocket:  # pragma: no cover - simple stub
        async def accept(self) -> None:
            return None

        async def send_text(self, _message: str) -> None:
            return None

    fastapi_module.WebSocket = WebSocket
    sys.modules["fastapi"] = fastapi_module


def _install_celery_stub() -> None:
    import types

    if "celery" in sys.modules:
        return

    celery_module = types.ModuleType("celery")

    class Celery:
        class _Config:
            def update(self, *_args, **_kwargs) -> None:
                return None

        def __init__(self, *_args, **_kwargs) -> None:  # noqa: ANN001
            self.conf = self._Config()

        def task(self, *task_args, **task_kwargs):  # noqa: ANN001
            def decorator(func):
                return func

            return decorator

    celery_module.Celery = Celery

    schedules_module = types.ModuleType("celery.schedules")

    def crontab(*_args, **_kwargs):  # noqa: ANN001
        return {"args": _args, "kwargs": _kwargs}

    schedules_module.crontab = crontab
    celery_module.schedules = schedules_module
    sys.modules["celery"] = celery_module
    sys.modules["celery.schedules"] = schedules_module


def _install_kombu_stub() -> None:
    import types

    if "kombu" in sys.modules:
        return

    kombu_module = types.ModuleType("kombu")

    class Queue:
        def __init__(self, name, *_args, **_kwargs) -> None:  # noqa: ANN001
            self.name = name

    kombu_module.Queue = Queue
    sys.modules["kombu"] = kombu_module


class DummyWebSocketManager:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    async def send_generation_progress(
        self,
        job_id: str,
        progress: float,
        user_id: int,
        status: str = "processing",
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(("progress", progress, message))

    async def send_generation_complete(
        self,
        job_id: str,
        payload: list[str],
        user_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(("complete", payload))

    async def send_generation_error(self, job_id: str, message: str, user_id: int) -> None:
        self.events.append(("error", message))


@pytest.fixture
def celery_remote_env(tmp_path, monkeypatch):
    for module in [
        "services.database",
        "services.model_repository",
        "services.model_manager",
        "services.generation_service",
        "workers.celery_app",
        "workers.generation_worker",
        "workers.video_worker",
    ]:
        sys.modules.pop(module, None)

    _ensure_pydantic_stack()
    _ensure_alembic_stub()
    _install_database_stub()
    _install_pil_stub()
    _install_fastapi_stub()
    _install_celery_stub()
    _install_kombu_stub()
    monkeypatch.setenv("SEIDRA_USE_REAL_MODELS", "0")
    db_path = tmp_path / "seidra.db"
    monkeypatch.setenv("SEIDRA_DATABASE_URL", f"sqlite:///{db_path}")

    from core import config

    config.get_settings.cache_clear()
    config.settings = config.Settings(
        media_dir=tmp_path / "media",
        thumbnail_dir=tmp_path / "thumbs",
        models_dir=tmp_path / "models",
        temp_dir=tmp_path / "tmp",
        comfyui_url="http://comfy.test",
        sadtalker_url="http://sadtalker.test",
        database_url=f"sqlite:///{db_path}",
    )

    from services import (
        database as database_module,
        generation_service as generation_service_module,
        model_manager as model_manager_module,
        model_repository as model_repository_module,
    )


    image_bytes = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAucB9o9pOwAAAABJRU5ErkJggg=="
    )
    video_bytes = b"FAKE-MP4-DATA"

    request_log: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_log.append((request.method, request.url.path))
        if request.url.host == "comfy.test" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "queue": {"pending": 0}})
        if request.url.host == "sadtalker.test" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.host == "comfy.test" and request.url.path == "/api/generate":
            return httpx.Response(
                200,
                json={
                    "images": [
                        {
                            "url": "http://comfy.test/assets/result.png",
                            "filename": "result.png",
                        }
                    ],
                    "metadata": {"sampler": "ddim"},
                },
            )
        if request.url.host == "comfy.test" and request.url.path == "/assets/result.png":
            return httpx.Response(200, content=image_bytes, headers={"content-type": "image/png"})
        if request.url.host == "comfy.test" and request.url.path == "/lora/test_lora.safetensors":
            return httpx.Response(200, content=b"lora-bytes")
        if request.url.host == "sadtalker.test" and request.url.path == "/api/generate":
            return httpx.Response(
                200,
                json={
                    "videos": [
                        {
                            "url": "http://sadtalker.test/assets/talk.mp4",
                            "filename": "talk.mp4",
                        }
                    ]
                },
            )
        if request.url.host == "sadtalker.test" and request.url.path == "/assets/talk.mp4":
            return httpx.Response(200, content=video_bytes, headers={"content-type": "video/mp4"})
        return httpx.Response(404, json={"error": "not-found"})

    transport = httpx.MockTransport(handler)

    manager = model_manager_module.ModelManager()
    manager._create_http_client = lambda: httpx.AsyncClient(transport=transport)
    manager.repository = model_repository_module.ModelRepository(
        manager.models_dir, http_client_factory=manager._create_http_client
    )
    manager.popular_loras = {
        "test_lora": {
            "url": "http://comfy.test/lora/test_lora.safetensors",
            "filename": "test_lora.safetensors",
            "category": "style",
        }
    }

    websocket_manager = DummyWebSocketManager()
    generation_service_module.configure_generation_service(manager, websocket_manager)

    from workers import (
        generation_worker as generation_worker_module,
        video_worker as video_worker_module,
    )


    db = database_module.DatabaseService()
    user = db.create_user("tester", "tester@example.com", "supersecurepassword")
    db.close()

    def create_job(job_type: str, prompt: str) -> str:
        job_id = str(uuid.uuid4())
        db_local = database_module.DatabaseService()
        parameters = {"prompt": prompt, "job_type": job_type}
        db_local.create_job(
            id=job_id,
            user_id=user.id,
            job_type=job_type,
            prompt=prompt,
            negative_prompt="",
            model_name="sadtalker" if job_type == "video" else "sdxl-base",
            lora_models=[],
            parameters=parameters,
            status="pending",
        )
        db_local.close()
        return job_id

    return {
        "manager": manager,
        "generation_worker": generation_worker_module,
        "video_worker": video_worker_module,
        "create_job": create_job,
        "media_dir": config.settings.media_directory,
        "image_bytes": image_bytes,
        "video_bytes": video_bytes,
        "request_log": request_log,
        "websocket_manager": websocket_manager,
    }


def test_celery_remote_image_generation(celery_remote_env):
    env = celery_remote_env
    job_id = env["create_job"]("image", "A calm sunset")
    task = env["generation_worker"].generate_images_task
    callable_task = getattr(task, "run", task)
    def retry_stub(exc=None, **kwargs):  # type: ignore[override]
        exc = exc or kwargs.get("exc") or RuntimeError("retry")
        raise exc

    task_instance = SimpleNamespace(request=SimpleNamespace(retries=0), max_retries=3, retry=retry_stub)
    result = callable_task(task_instance, job_id, {"prompt": "A calm sunset"})

    assert result["status"] == "completed"
    assert len(result["result_images"]) == 1

    image_path = Path(result["result_images"][0])
    assert image_path.exists()
    assert image_path.read_bytes() == env["image_bytes"]

    assert ("POST", "/api/generate") in env["request_log"]
    assert any(event[0] == "complete" for event in env["websocket_manager"].events)

    status = env["manager"].get_status_snapshot()
    assert status["mode"] == "remote"
    assert status["last_generation"]["type"] == "image"


def test_celery_remote_video_generation(celery_remote_env):
    env = celery_remote_env
    job_id = env["create_job"]("video", "Say hello")
    task = env["video_worker"].generate_video_task
    callable_task = getattr(task, "run", task)
    def retry_stub(exc=None, **kwargs):  # type: ignore[override]
        exc = exc or kwargs.get("exc") or RuntimeError("retry")
        raise exc

    task_instance = SimpleNamespace(request=SimpleNamespace(retries=0), max_retries=3, retry=retry_stub)
    result = callable_task(task_instance, job_id, {"prompt": "Say hello"})

    assert result["status"] == "completed"
    assert len(result["result_videos"]) == 1

    video_path = Path(result["result_videos"][0])
    assert video_path.exists()
    assert video_path.read_bytes() == env["video_bytes"]

    assert ("POST", "/api/generate") in env["request_log"]