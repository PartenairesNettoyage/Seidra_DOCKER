from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote

from api import auth as auth_module
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture()
def media_test_app(tmp_path, monkeypatch):
    from api import media as media_module

    export_dir = tmp_path / "exports"
    monkeypatch.setattr(media_module, "EXPORT_BASE_DIR", export_dir.resolve())
    monkeypatch.setattr(auth_module.settings, "allow_system_fallback", True, raising=False)

    source_file = tmp_path / "media" / "image.png"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_bytes(b"fake-image")

    now = datetime.utcnow()

    def _database_factory():
        class _DummyDatabase:
            def __init__(self):
                self._closed = False

            def get_media_items(self, **kwargs):
                item = SimpleNamespace(
                    id="media-1",
                    user_id=1,
                    job_id="job-1",
                    file_path=str(source_file),
                    thumbnail_path=None,
                    file_type="image",
                    mime_type="image/png",
                    metadata_payload={"prompt": "test"},
                    tags=["test"],
                    is_favorite=False,
                    is_nsfw=False,
                    nsfw_tags=[],
                    created_at=now,
                )
                return [item], 1

            def close(self):
                self._closed = True

        return _DummyDatabase()

    monkeypatch.setattr(media_module, "DatabaseService", _database_factory)

    app = FastAPI()
    app.include_router(media_module.router, prefix="/media")

    fallback_user_id = auth_module._fallback_user().id

    with TestClient(app) as client:
        yield client, export_dir.resolve(), fallback_user_id


def test_export_media_creates_zip_in_export_dir(media_test_app):
    client, export_dir, user_id = media_test_app

    response = client.post(
        "/media/export",
        json={"media_ids": ["media-1"], "format": "zip", "include_metadata": True},
    )

    assert response.status_code == 200
    payload = response.json()

    export_file = payload["export_file"]
    user_export_dir = export_dir / str(user_id)
    export_path = user_export_dir / export_file
    assert export_path.exists()
    assert export_path.is_file()

    assert payload["download_url"] == f"/api/media/download-export/{export_file}"

    download_response = client.get(f"/media/download-export/{export_file}")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/zip"


@pytest.mark.parametrize(
    "malicious_name",
    ["..\\secret.zip", "archive..zip"],
)
def test_download_export_rejects_malicious_names(media_test_app, malicious_name):
    client, _, _ = media_test_app

    encoded_name = quote(malicious_name, safe="")
    response = client.get(f"/media/download-export/{encoded_name}")

    assert response.status_code == 400
    assert "Invalid export file name" in response.json()["detail"]


def test_download_export_rejects_parent_directory_sequences(tmp_path, monkeypatch):
    import asyncio

    from api import media as media_module
    from fastapi import HTTPException

    export_dir = tmp_path / "exports"
    monkeypatch.setattr(media_module, "EXPORT_BASE_DIR", export_dir.resolve())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(media_module.download_export("../secret.zip", SimpleNamespace(id=1)))

    assert exc.value.status_code == 400
    assert "Invalid export file name" in exc.value.detail


def test_download_export_requires_auth_without_token(media_test_app, monkeypatch):
    client, _, _ = media_test_app

    monkeypatch.setattr(auth_module.settings, "allow_system_fallback", False, raising=False)

    response = client.get("/media/download-export/export.zip")

    assert response.status_code == 401
