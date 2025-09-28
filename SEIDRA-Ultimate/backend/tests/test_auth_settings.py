from datetime import datetime
from types import SimpleNamespace

from api.auth import router, verify_token
from api.settings import DEFAULT_SETTINGS
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def fake_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        username="demo",
        email="demo@example.com",
        is_active=True,
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def test_app(fake_user: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/auth")
    app.dependency_overrides[verify_token] = lambda: fake_user
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


def test_update_user_settings_success(monkeypatch: pytest.MonkeyPatch, client: TestClient, fake_user: SimpleNamespace):
    updated_settings = {
        "theme": "midnight",
        "telemetry_opt_in": False,
        "extra": {"beta": True},
    }

    class DummyDB:
        def __init__(self):
            pass

        def update_user_settings(self, user_id: int, **settings_updates):
            assert user_id == fake_user.id
            assert settings_updates == updated_settings
            return SimpleNamespace(settings=settings_updates)

        def close(self):
            pass

    monkeypatch.setattr("api.auth.DatabaseService", DummyDB)

    response = client.put("/api/auth/me/settings", json=updated_settings)
    assert response.status_code == 200

    data = response.json()
    assert data["theme"] == updated_settings["theme"]
    assert data["telemetry_opt_in"] is False
    assert data["language"] == DEFAULT_SETTINGS["language"]
    assert data["notifications"] == DEFAULT_SETTINGS["notifications"]
    assert data["extra"] == updated_settings["extra"]


def test_update_user_settings_user_not_found(monkeypatch: pytest.MonkeyPatch, client: TestClient, fake_user: SimpleNamespace):
    class DummyDB:
        def __init__(self):
            pass

        def update_user_settings(self, user_id: int, **settings_updates):
            assert user_id == fake_user.id
            return None

        def close(self):
            pass

    monkeypatch.setattr("api.auth.DatabaseService", DummyDB)

    response = client.put("/api/auth/me/settings", json={"theme": "midnight"})
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_partial_notification_update_preserves_other_channels(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from services import database as database_module

    db_file = tmp_path / "settings.db"
    test_engine = create_engine(f"sqlite:///{db_file}", future=True)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    database_module.Base.metadata.create_all(bind=test_engine)

    monkeypatch.setattr(database_module, "engine", test_engine, raising=False)
    monkeypatch.setattr(database_module, "SessionLocal", TestSessionLocal, raising=False)
    monkeypatch.setattr(database_module.secret_manager, "get", lambda key: None, raising=False)
    monkeypatch.setattr(database_module, "_SCHEMA_INITIALISED", True, raising=False)

    service = database_module.DatabaseService()

    try:
        user = service.create_user("notif", "notif@example.com", "hashed")
        service.update_user_settings(user.id, notifications={"web": False})
        user = service.update_user_settings(user.id, notifications={"email": True})

        notifications = user.settings.get("notifications", {})

        assert notifications["web"] is False
        assert notifications["email"] is True
        assert notifications["slack"] is DEFAULT_SETTINGS["notifications"]["slack"]
    finally:
        service.close()
        test_engine.dispose()


def test_verify_token_returns_system_user_when_flag_enabled(monkeypatch: pytest.MonkeyPatch):
    from api import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "allow_system_fallback", True, raising=False)

    user = auth_module.verify_token(None)
    assert user.username == "system"
    assert getattr(user, "is_system", False) is True
    assert user.email == "system@seidra.local"
    # created_at is stored as an ISO 8601 string for compatibility with UserResponse
    datetime.fromisoformat(user.created_at)
    assert user.settings == DEFAULT_SETTINGS


def test_verify_token_requires_token_when_flag_disabled(monkeypatch: pytest.MonkeyPatch):
    from api import auth as auth_module

    monkeypatch.setattr(auth_module.settings, "allow_system_fallback", False, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        auth_module.verify_token(None)

    exception = exc_info.value
    assert exception.status_code == status.HTTP_401_UNAUTHORIZED
