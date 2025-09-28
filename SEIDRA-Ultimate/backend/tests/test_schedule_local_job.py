import importlib
import sys
import types


def _install_fastapi_stub(monkeypatch):
    fastapi_stub = types.ModuleType("fastapi")

    class _StubAPIRouter:
        def __init__(self, *_args, **_kwargs):
            return None

        def _decorator(self, *_args, **_kwargs):
            def wrapper(func):
                return func

            return wrapper

        post = _decorator
        get = _decorator
        delete = _decorator

    class _StubBackgroundTasks:
        def add_task(self, *_args, **_kwargs):
            return None

    class _StubHTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def _depends(dependency):
        return dependency

    fastapi_stub.APIRouter = _StubAPIRouter
    fastapi_stub.BackgroundTasks = _StubBackgroundTasks
    fastapi_stub.HTTPException = _StubHTTPException
    fastapi_stub.Depends = _depends

    monkeypatch.setitem(sys.modules, "fastapi", fastapi_stub)


def _install_pydantic_stub(monkeypatch):
    pydantic_stub = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def dict(self, *_args, **_kwargs):
            return dict(self.__dict__)

        def model_dump(self, *_args, **_kwargs):
            return dict(self.__dict__)

    def _field(default=None, **_kwargs):
        return default

    class _ConfigDict(dict):
        pass

    pydantic_stub.BaseModel = _BaseModel
    pydantic_stub.Field = _field
    pydantic_stub.ConfigDict = _ConfigDict

    monkeypatch.setitem(sys.modules, "pydantic", pydantic_stub)


def _install_generation_service_stub(monkeypatch):
    generation_service_stub = types.ModuleType("services.generation_service")

    class _Service:
        async def notify_job_queued(self, *_args, **_kwargs):
            return None

        async def enqueue_job(self, *_args, **_kwargs):
            return None

        async def notify_batch_queued(self, *_args, **_kwargs):
            return None

        async def process_video_job(self, *_args, **_kwargs):
            return None

    def _get_generation_service():
        return _Service()

    generation_service_stub.get_generation_service = _get_generation_service

    monkeypatch.setitem(sys.modules, "services.generation_service", generation_service_stub)


def _install_worker_stubs(monkeypatch):
    workers_generation_stub = types.ModuleType("workers.generation_worker")
    workers_generation_stub.submit_batch_generation_job = lambda *args, **kwargs: None
    workers_generation_stub.submit_generation_job = lambda *args, **kwargs: None
    workers_generation_stub.generate_images_task = lambda *args, **kwargs: None
    workers_generation_stub.batch_generate_images_task = lambda *args, **kwargs: None
    monkeypatch.setitem(
        sys.modules, "workers.generation_worker", workers_generation_stub
    )

    workers_video_stub = types.ModuleType("workers.video_worker")
    workers_video_stub.generate_video_task = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "workers.video_worker", workers_video_stub)


def _install_auth_stub(monkeypatch):
    auth_stub = types.ModuleType("api.auth")

    def _verify_token():  # pragma: no cover - not used directly
        return types.SimpleNamespace(id=1)

    auth_stub.verify_token = _verify_token
    monkeypatch.setitem(sys.modules, "api.auth", auth_stub)


def _install_database_stub(monkeypatch):
    database_stub = types.ModuleType("services.database")

    class _DatabaseService:
        def __init__(self, *_args, **_kwargs):
            return None

        def close(self):
            return None

    database_stub.DatabaseService = _DatabaseService
    monkeypatch.setitem(sys.modules, "services.database", database_stub)


def test_schedule_local_job_runs_enqueue(monkeypatch):
    _install_fastapi_stub(monkeypatch)
    _install_pydantic_stub(monkeypatch)
    _install_generation_service_stub(monkeypatch)
    _install_worker_stubs(monkeypatch)
    _install_auth_stub(monkeypatch)
    _install_database_stub(monkeypatch)

    existing_module = sys.modules.pop("api.generation", None)
    try:
        generation = importlib.import_module("api.generation")

        notifications: list[str] = []
        enqueued: list[tuple[str, dict, str]] = []

        async def _notify(job_id: str):
            notifications.append(job_id)

        async def _enqueue(job_id: str, request: dict, priority_tag: str):
            enqueued.append((job_id, request, priority_tag))

        monkeypatch.setattr(
            generation,
            "_generation_service",
            types.SimpleNamespace(
                notify_job_queued=_notify,
                enqueue_job=_enqueue,
            ),
        )

        payload = {"prompt": "hello"}
        generation.schedule_local_job("job-123", payload, "realtime")

        assert notifications == ["job-123"]
        assert enqueued == [("job-123", payload, "realtime")]
    finally:
        if existing_module is not None:
            sys.modules["api.generation"] = existing_module
        else:
            sys.modules.pop("api.generation", None)
