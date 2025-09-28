from datetime import datetime, timedelta
from pathlib import Path
import sys
import types
import uuid

import pytest


def _ensure_alembic_stub() -> None:
    if "alembic" in sys.modules:
        return

    command_module = types.ModuleType("alembic.command")
    command_module.upgrade = lambda *_, **__: None

    config_module = types.ModuleType("alembic.config")

    class _Config:
        def __init__(self, *args, **kwargs):
            pass

        def set_main_option(self, *args, **kwargs):
            return None

    config_module.Config = _Config

    alembic_module = types.ModuleType("alembic")
    alembic_module.command = command_module
    alembic_module.config = config_module

    sys.modules.setdefault("alembic", alembic_module)
    sys.modules.setdefault("alembic.command", command_module)
    sys.modules.setdefault("alembic.config", config_module)


@pytest.fixture()
def db_service(tmp_path, monkeypatch):
    _ensure_alembic_stub()
    from services import database as database_module

    original_engine = database_module.engine
    original_session_local = database_module.SessionLocal

    test_db_path = tmp_path / "media_filters.db"
    monkeypatch.setenv("SEIDRA_DATABASE_URL", f"sqlite:///{test_db_path}")

    db = database_module.DatabaseService()
    test_engine = database_module.engine
    Base = database_module.Base
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()
        database_module.engine = original_engine
        database_module.SessionLocal = original_session_local


def _create_user_personas(db):
    user = db.create_user("media-user", "media@example.com", "hashed")
    persona_one = db.create_persona(
        user.id,
        name="Explorer",
        description="",
        style_prompt="style",
    )
    persona_two = db.create_persona(
        user.id,
        name="Artist",
        description="",
        style_prompt="style",
    )
    return user, persona_one, persona_two


def _create_job(db, user_id, persona_id=None, prompt="Prompt"):
    job_id = f"job-{uuid.uuid4()}"
    return db.create_job(
        id=job_id,
        user_id=user_id,
        persona_id=persona_id,
        job_type="image",
        prompt=prompt,
        negative_prompt="",
        model_name="model",
        parameters={"cfg": 7},
        status="completed",
    )


def test_get_media_items_filters_combination(db_service):
    user, persona_one, persona_two = _create_user_personas(db_service)
    job_one = _create_job(db_service, user.id, persona_one.id, prompt="Sunset cliffs")
    job_two = _create_job(db_service, user.id, persona_two.id, prompt="Studio portrait")
    job_three = _create_job(db_service, user.id, persona_one.id, prompt="City skyline")

    base = datetime(2024, 1, 1, 12, 0, 0)

    db_service.create_media_item(
        id="media-1",
        user_id=user.id,
        job_id=job_one.id,
        file_path=str(Path("/tmp/media-1.png")),
        file_type="image",
        mime_type="image/png",
        metadata={"prompt": "Sunset cliffs"},
        tags=["Sunset", "Landscape"],
        is_favorite=True,
        created_at=base,
    )
    db_service.create_media_item(
        id="media-2",
        user_id=user.id,
        job_id=job_two.id,
        file_path=str(Path("/tmp/media-2.png")),
        file_type="image",
        mime_type="image/png",
        metadata={"prompt": "Studio portrait"},
        tags=["Portrait"],
        is_favorite=False,
        created_at=base + timedelta(hours=1),
    )
    db_service.create_media_item(
        id="media-3",
        user_id=user.id,
        job_id=job_three.id,
        file_path=str(Path("/tmp/media-3.png")),
        file_type="image",
        mime_type="image/png",
        metadata={"prompt": "City skyline"},
        tags=["Night", "City"],
        is_favorite=False,
        created_at=base + timedelta(hours=2),
    )

    items, total = db_service.get_media_items(user.id, favorites_only=True)
    assert total == 1
    assert [item.id for item in items] == ["media-1"]

    items, total = db_service.get_media_items(user.id, persona_id=persona_one.id)
    assert total == 2
    assert {item.id for item in items} == {"media-1", "media-3"}

    items, total = db_service.get_media_items(user.id, tags=["night"])  # case-insensitive
    assert total == 1
    assert items[0].id == "media-3"

    items, total = db_service.get_media_items(user.id, search="portrait")
    assert total == 1
    assert items[0].id == "media-2"

    items, total = db_service.get_media_items(
        user.id,
        tags=["city"],
        search="city",
        date_from=base + timedelta(minutes=30),
        date_to=base + timedelta(hours=3),
    )
    assert total == 1
    assert items[0].id == "media-3"


def test_get_media_items_respects_pagination(db_service):
    user, persona_one, _ = _create_user_personas(db_service)
    job = _create_job(db_service, user.id, persona_one.id)

    base = datetime(2024, 2, 1, 10, 0, 0)
    total_items = 60
    for index in range(total_items):
        db_service.create_media_item(
            id=f"media-{index}",
            user_id=user.id,
            job_id=job.id,
            file_path=str(Path(f"/tmp/media-{index}.png")),
            file_type="image",
            mime_type="image/png",
            metadata={"prompt": f"Prompt {index}"},
            tags=["batch", str(index % 3)],
            is_favorite=index % 2 == 0,
            created_at=base + timedelta(minutes=index),
        )

    items, total = db_service.get_media_items(user.id, limit=15, offset=20)
    assert total == total_items
    assert len(items) == 15

    expected_ids = [f"media-{total_items - 1 - offset}" for offset in range(20, 35)]
    assert [item.id for item in items] == expected_ids
