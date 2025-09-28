from datetime import datetime

from api import auth as auth_module
from api.settings_models import DEFAULT_SETTINGS
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_get_me_returns_system_user_when_fallback_enabled(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "allow_system_fallback", True, raising=False)

    app = FastAPI()
    app.include_router(auth_module.router, prefix="/api/auth")

    with TestClient(app) as client:
        response = client.get("/api/auth/me")

    assert response.status_code == 200

    payload = response.json()
    assert payload["id"] == 1
    assert payload["username"] == "system"
    assert payload["email"] == "system@seidra.local"
    assert payload["is_active"] is True
    datetime.fromisoformat(payload["created_at"])
    assert payload["settings"] == DEFAULT_SETTINGS


def test_register_user_with_existing_email_returns_400(monkeypatch):
    app = FastAPI()
    app.include_router(auth_module.router, prefix="/api/auth")

    class DummyUser:
        def __init__(self, user_id: int, username: str, email: str, hashed_password: str):
            self.id = user_id
            self.username = username
            self.email = email
            self.hashed_password = hashed_password
            self.is_active = True
            self.created_at = datetime.utcnow()
            self.settings = {}

    class DummyDatabaseService:
        def __init__(self):
            self._users = []

        def close(self):
            pass

        def get_user_by_username(self, username: str):
            return next((user for user in self._users if user.username == username), None)

        def get_user_by_email(self, email: str):
            return next((user for user in self._users if user.email == email), None)

        def create_user(self, username: str, email: str, hashed_password: str):
            user = DummyUser(len(self._users) + 1, username, email, hashed_password)
            self._users.append(user)
            return user

    dummy_db = DummyDatabaseService()
    dummy_db.create_user("existing_user", "existing@example.com", "hashed")

    monkeypatch.setattr(auth_module, "DatabaseService", lambda: dummy_db)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "username": "new_user",
                "email": "existing@example.com",
                "password": "supersecretpassword",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"
