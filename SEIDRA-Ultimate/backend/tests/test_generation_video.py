import asyncio
import base64
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from .test_model_manager_mock import (
    _ensure_httpx_stub,
    _ensure_pil_stub,
    _ensure_pydantic_stack,
)

try:  # pragma: no cover - optional dependency for API integration tests
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - handled by fixtures when missing
    FastAPI = TestClient = None


@pytest.fixture()
def generation_test_app(tmp_path):
    pytest.importorskip("fastapi")

    db_path = tmp_path / "video_jobs.db"
    os.environ["SEIDRA_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SEIDRA_MEDIA_DIR"] = str(tmp_path / "media")
    os.environ["SEIDRA_THUMBNAIL_DIR"] = str(tmp_path / "thumbs")
    os.environ["SEIDRA_MODELS_DIR"] = str(tmp_path / "models")
    os.environ["SEIDRA_TMP_DIR"] = str(tmp_path / "tmp")

    for module_name in [
        "api.generation",
        "core.config",
        "services.database",
        "services.generation_service",
        "services.model_manager",
        "workers.video_worker",
    ]:
        sys.modules.pop(module_name, None)

    database_module = importlib.import_module("services.database")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database_module.engine.dispose()
    database_module.engine = create_engine(
        os.environ["SEIDRA_DATABASE_URL"], echo=False, future=True
    )
    database_module.SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=database_module.engine,
    )

    Base = database_module.Base
    Base.metadata.create_all(bind=database_module.engine)

    db = database_module.DatabaseService()
    try:
        db.create_user("tester", "tester@example.com", "hashed-password")
    finally:
        db.close()

    generation_service_module = importlib.import_module("services.generation_service")

    class StubGenerationService:
        async def notify_job_queued(self, job_id: str):
            return None

        async def enqueue_job(self, job_id: str, request: dict, priority_tag: str = "realtime"):
            return {"job_id": job_id, **request}

        async def notify_batch_queued(self, job_ids):
            return None

        async def process_video_job(self, job_id: str, request_data: dict):
            return {"job_id": job_id, "status": "completed", "result_videos": []}

    stub_service = StubGenerationService()
    generation_service_module._generation_service = stub_service

    def _get_stub_service():
        return stub_service

    generation_service_module.get_generation_service = _get_stub_service

    generation_module = importlib.import_module("api.generation")

    app = FastAPI()
    app.include_router(generation_module.router, prefix="/generate")
    app.dependency_overrides[generation_module.verify_token] = lambda: SimpleNamespace(id=1)

    with TestClient(app) as client:
        yield client, generation_module, database_module.DatabaseService

    Base.metadata.drop_all(bind=database_module.engine)


def test_video_generation_validation_error(generation_test_app):
    client, _, _ = generation_test_app

    response = client.post(
        "/generate/video",
        data={"prompt": "", "duration_seconds": "0"},
        files={"audio_file": ("invalid.wav", b"bad", "audio/wav")},
    )

    assert response.status_code == 422


def test_video_generation_persists_job_and_notifies(generation_test_app, monkeypatch):
    client, generation_module, DatabaseService = generation_test_app

    monkeypatch.setattr(generation_module, "USE_CELERY", False)

    notifications = []
    processed = []

    async def fake_notify(self, job_id):
        notifications.append(job_id)

    async def fake_process(self, job_id, request_data):
        processed.append((job_id, request_data))
        return {"job_id": job_id, "status": "completed", "result_videos": []}

    service_cls = generation_module._generation_service.__class__
    monkeypatch.setattr(service_cls, "notify_job_queued", fake_notify)
    monkeypatch.setattr(service_cls, "process_video_job", fake_process)

    payload = {
        "prompt": "Create a narrated timelapse",
        "reference_image": "scene.png",
        "duration_seconds": "8",
        "model_name": "sadtalker",
        "metadata": json.dumps({"source": "unit-test"}),
    }

    response = client.post(
        "/generate/video",
        data=payload,
        files={"audio_file": ("voice.mp3", b"audio-bytes", "audio/mpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    job_id = body["job_id"]
    assert body["status"] == "queued"
    assert "Video generation job queued" in body["message"]

    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        assert job is not None
        assert job.job_type == "video"
        assert job.prompt == payload["prompt"]
        assert job.model_name == payload["model_name"]
        assert job.parameters["duration_seconds"] == int(payload["duration_seconds"])
        assert job.metadata_payload["source"] == "unit-test"
        assert Path(job.metadata_payload["audio_path"]).exists()
    finally:
        db.close()

    assert job_id in notifications
    assert processed and processed[0][0] == job_id
    processed_payload = processed[0][1]
    assert processed_payload["prompt"] == payload["prompt"]
    assert processed_payload["duration_seconds"] == int(payload["duration_seconds"])
    assert Path(processed_payload["audio_path"]).exists()
    artifact = processed_payload["audio_artifact"]
    assert artifact["encoding"] == "base64"
    assert base64.b64decode(artifact["data"]) == b"audio-bytes"
    assert processed_payload["metadata"]["source"] == "unit-test"


def test_video_generation_uses_celery_when_enabled(generation_test_app, monkeypatch):
    client, generation_module, DatabaseService = generation_test_app

    monkeypatch.setattr(generation_module, "USE_CELERY", True)

    class StubTask:
        def __init__(self):
            self.calls = []

        def delay(self, job_id, request_data):
            self.calls.append((job_id, request_data))

    stub_task = StubTask()
    monkeypatch.setattr(generation_module, "generate_video_task", stub_task)

    queued = []

    def fake_schedule(job_id):
        queued.append(job_id)

    monkeypatch.setattr(
        generation_module,
        "schedule_job_queued_notification",
        fake_schedule,
    )

    payload = {"prompt": "Lip sync demo", "duration_seconds": "4"}
    response = client.post(
        "/generate/video",
        data=payload,
        files={"audio_file": ("voice.wav", b"payload", "audio/wav")},
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]

    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        assert job is not None
        assert job.job_type == "video"
    finally:
        db.close()

    assert len(stub_task.calls) == 1
    celery_job_id, celery_payload = stub_task.calls[0]
    assert celery_job_id == job_id
    assert celery_payload["prompt"] == payload["prompt"]
    assert celery_payload["duration_seconds"] == int(payload["duration_seconds"])
    assert celery_payload["model_name"] == "sadtalker"
    assert celery_payload["metadata"] == {}
    assert Path(celery_payload["audio_path"]).exists()
    celery_artifact = celery_payload["audio_artifact"]
    assert celery_artifact["encoding"] == "base64"
    assert base64.b64decode(celery_artifact["data"]) == b"payload"
    assert queued == [job_id]


def test_model_manager_remote_uses_audio_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("SEIDRA_USE_REAL_MODELS", "0")

    media_dir = tmp_path / "media"
    models_dir = tmp_path / "models"
    thumbs_dir = tmp_path / "thumbs"
    tmp_dir = tmp_path / "tmp"

    _ensure_pydantic_stack()
    _ensure_httpx_stub()
    _ensure_pil_stub()

    from core import config as config_module

    importlib.reload(config_module)
    config_module.get_settings.cache_clear()
    config_module.settings = config_module.Settings(
        media_dir=media_dir,
        thumbnail_dir=thumbs_dir,
        models_dir=models_dir,
        temp_dir=tmp_dir,
        comfyui_url="http://comfy.test",
        sadtalker_url="http://sadtalker.test",
    )

    from services import model_manager as model_manager_module

    importlib.reload(model_manager_module)
    manager = model_manager_module.ModelManager()
    manager.use_mock_pipeline = False

    audio_path = tmp_path / "voice.wav"
    audio_bytes = b"stream-bytes"
    audio_path.write_bytes(audio_bytes)

    audio_artifact = {
        "filename": "voice.wav",
        "content_type": "audio/wav",
        "encoding": "base64",
        "data": base64.b64encode(audio_bytes).decode("ascii"),
    }

    captured_request: dict = {}

    class DummyResponse:
        def __init__(self):
            self._payload = {
                "videos": [
                    {
                        "filename": "result.mp4",
                        "data": base64.b64encode(b"video-bytes").decode("ascii"),
                    }
                ]
            }

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    async def fake_post(_self, url, data=None, json=None, files=None):
        captured_request["url"] = url
        captured_request["data"] = data
        captured_request["json"] = json
        captured_request["files"] = files
        return DummyResponse()

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, json=None, files=None):
            return await fake_post(self, url, data=data, json=json, files=files)

    async def fake_persist(_client, payload, destination, base_url):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(base64.b64decode(payload["data"]))

    monkeypatch.setattr(manager, "_create_http_client", lambda: DummyClient())
    monkeypatch.setattr(manager, "_persist_remote_payload", fake_persist)
    monkeypatch.setattr(manager, "_sadtalker_endpoint", lambda route: "http://sadtalker.test/api/generate")

    outputs = asyncio.run(
        manager._generate_video_remote(
            prompt="Describe scene",
            reference_image=None,
            audio_path=str(audio_path),
            audio_artifact=audio_artifact,
            duration_seconds=6,
            model_name="sadtalker",
            media_dir=media_dir,
        )
    )

    assert captured_request["json"] is None
    assert "audio_path" not in captured_request["data"]
    assert captured_request["files"]["audio_file"][0] == "voice.wav"
    assert captured_request["files"]["audio_file"][1] == audio_bytes
    assert captured_request["files"]["audio_file"][2].startswith("audio/")
    assert outputs and Path(outputs[0]).exists()
