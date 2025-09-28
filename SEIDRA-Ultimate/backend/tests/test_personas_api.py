import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# Configure a dedicated SQLite database before importing the services layer
TEST_DB_PATH = Path(__file__).parent / "test_personas.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["SEIDRA_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"  # noqa: E501

for module_name in ("core.config", "services.database"):
    sys.modules.pop(module_name, None)

from api.auth import verify_token  # noqa: E402
from api.personas import router as personas_router  # noqa: E402
from services import database as database_module_reloaded  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

database_url = f"sqlite:///{TEST_DB_PATH}"
database_module_reloaded.engine.dispose()
database_module_reloaded.engine = create_engine(database_url, echo=False, future=True)
database_module_reloaded.SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=database_module_reloaded.engine,
)

Base = database_module_reloaded.Base
engine = database_module_reloaded.engine
DatabaseService = database_module_reloaded.DatabaseService


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = DatabaseService()
    try:
        # Create demo user with id=1
        user = db.create_user("tester", "tester@example.com", "secret")
        assert user.id == 1

        db.create_persona(
            user_id=user.id,
            name="Aria Daydream",
            description="A dreamy storyteller persona",
            style_prompt="cinematic portrait, soft lighting",
            negative_prompt="low quality, blurry",
            lora_models=["dream-lora"],
            generation_params={"width": 768, "height": 768, "num_inference_steps": 30},
            tags=["story", "dream"],
            is_favorite=True,
            is_nsfw=False,
        )
        db.create_persona(
            user_id=user.id,
            name="Neon Muse",
            description="Vibrant cyberpunk artist",
            style_prompt="neon lights, cyberpunk city",
            negative_prompt="dull colors",
            lora_models=[],
            generation_params={"width": 640, "height": 832, "num_inference_steps": 25},
            tags=["cyberpunk", "artist"],
            is_favorite=False,
            is_nsfw=False,
        )
        db.create_persona(
            user_id=user.id,
            name="Midnight Siren",
            description="Mysterious performer",
            style_prompt="noir stage, spotlight",
            negative_prompt="grainy",
            lora_models=[],
            generation_params={"width": 512, "height": 512, "num_inference_steps": 20},
            tags=["performer"],
            is_favorite=False,
            is_nsfw=True,
        )
    finally:
        db.close()

    yield

    Base.metadata.drop_all(bind=engine)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(personas_router, prefix="/personas")
    fake_user = SimpleNamespace(id=1, username="tester")
    app.dependency_overrides[verify_token] = lambda: fake_user

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_persona_list_filters_and_pagination(client):
    response = client.get("/personas", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    assert response.headers["X-Total-Count"] == "2"

    payload = response.json()
    assert len(payload) == 2
    assert all("tags" in persona for persona in payload)
    assert payload[0]["is_favorite"] in {True, False}

    search_response = client.get("/personas", params={"search": "neon"})
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert len(search_payload) == 1
    assert search_payload[0]["name"] == "Neon Muse"


def test_persona_list_includes_and_filters_nsfw(client):
    response = client.get("/personas")
    names = {persona["name"] for persona in response.json()}
    assert "Midnight Siren" not in names

    nsfw_response = client.get("/personas", params={"include_nsfw": True})
    nsfw_names = {persona["name"] for persona in nsfw_response.json()}
    assert "Midnight Siren" in nsfw_names


def test_persona_list_favorite_filter(client):
    response = client.get("/personas", params={"is_favorite": True})
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "Aria Daydream"
    assert payload[0]["is_favorite"] is True


def test_preview_endpoint_creates_mock_job(client):
    preview_response = client.post("/personas/1/preview")
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["status"] == "queued"
    assert preview_payload["persona_id"] == 1
    job_id = preview_payload["job_id"]

    time.sleep(0.2)
    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        assert job is not None
        assert job.job_type == "persona_preview"
        assert job.metadata_payload.get("preview") is True
        assert job.parameters.get("preview") is True
        assert job.persona_id == 1
        assert job.result_images
    finally:
        db.close()
