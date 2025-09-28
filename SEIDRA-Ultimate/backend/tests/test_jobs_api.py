import os
from pathlib import Path
import sys
import types
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

TEST_DB_PATH = Path(__file__).parent / "test_jobs.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["SEIDRA_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["SEIDRA_ALLOW_SYSTEM_FALLBACK"] = "1"

generation_stub = types.ModuleType("api.generation")
generation_stub.USE_CELERY = False


def _noop_schedule(*_args, **_kwargs):  # pragma: no cover - stub
    return None


generation_stub.schedule_local_job = _noop_schedule
sys.modules.setdefault("api.generation", generation_stub)

for module_name in (
    "core.config",
    "services.database",
    "services.generation_service",
    "api.jobs",
):
    sys.modules.pop(module_name, None)

from api.auth import verify_token  # noqa: E402
from services import database as database_module  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

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
DatabaseService = database_module.DatabaseService

from api.jobs import _generation_service, router as jobs_router  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=database_module.engine)
    Base.metadata.create_all(bind=database_module.engine)

    db = DatabaseService()
    try:
        db.create_user("tester", "tester@example.com", "secret")
    finally:
        db.close()

    yield

    Base.metadata.drop_all(bind=database_module.engine)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(jobs_router, prefix="/jobs")

    fake_user = SimpleNamespace(id=1, username="tester", is_system=True)
    app.dependency_overrides[verify_token] = lambda: fake_user

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class StubWebSocketManager:
    def __init__(self):
        self.events = []

    async def dispatch_event(self, message, *, channels=None, user_id=None):
        self.events.append(
            {
                "message": message,
                "channels": set(channels or []),
                "user_id": user_id,
            }
        )


def test_cancel_job_dispatches_event(client):
    job_id = str(uuid.uuid4())

    db = DatabaseService()
    try:
        db.create_job(
            id=job_id,
            user_id=1,
            persona_id=None,
            job_type="image",
            prompt="Generate a castle",
            negative_prompt="",
            model_name="test-model",
            lora_models=[],
            parameters={"width": 512, "height": 512},
            status="processing",
        )
    finally:
        db.close()

    stub_manager = StubWebSocketManager()
    original_manager = _generation_service.websocket_manager
    _generation_service.websocket_manager = stub_manager

    try:
        response = client.post(f"/jobs/{job_id}/cancel")
    finally:
        _generation_service.websocket_manager = original_manager

    assert response.status_code == 200
    assert stub_manager.events == [
        {
            "message": {"type": "job_cancelled", "job_id": job_id},
            "channels": {"jobs"},
            "user_id": 1,
        }
    ]

    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        assert job.status == "cancelled"
    finally:
        db.close()
