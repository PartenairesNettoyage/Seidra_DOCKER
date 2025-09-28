"""Tests for the model download background task."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import types


class _StubBackgroundTasks:
    def add_task(self, *args, **kwargs):  # pragma: no cover - behaviour irrelevant
        pass


class _StubHTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _StubAPIRouter:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def post(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def delete(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


class _StubBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _stub_field(*args, default=None, default_factory=None, **kwargs):
    if default_factory is not None:
        return default_factory()
    return default


class _StubModelManager:
    def __init__(self, *args, **kwargs):  # pragma: no cover - placeholder
        pass


def test_download_task_honours_models_directory_env(monkeypatch, tmp_path):
    """The download task should respect ``SEIDRA_MODELS_DIR`` when writing files."""

    # Provide lightweight stand-ins for optional dependencies used during import.
    fastapi_stub = types.SimpleNamespace(
        APIRouter=_StubAPIRouter,
        BackgroundTasks=_StubBackgroundTasks,
        Depends=lambda dependency: dependency,
        HTTPException=_StubHTTPException,
    )
    pydantic_stub = types.SimpleNamespace(BaseModel=_StubBaseModel, Field=_stub_field)
    services_module = types.ModuleType("services")
    services_module.__path__ = []  # type: ignore[attr-defined]
    services_database_stub = types.ModuleType("services.database")
    services_database_stub.DatabaseService = object  # placeholder, patched later
    services_model_manager_stub = types.ModuleType("services.model_manager")
    services_model_manager_stub.ModelManager = _StubModelManager
    api_auth_stub = types.ModuleType("api.auth")
    api_auth_stub.verify_token = lambda: None
    core_module = types.ModuleType("core")
    core_module.__path__ = []  # type: ignore[attr-defined]
    core_config_stub = types.ModuleType("core.config")
    core_config_stub.settings = types.SimpleNamespace(models_directory=Path("."))

    monkeypatch.setitem(sys.modules, "fastapi", fastapi_stub)
    monkeypatch.setitem(sys.modules, "pydantic", pydantic_stub)
    monkeypatch.setitem(sys.modules, "services", services_module)
    monkeypatch.setitem(sys.modules, "services.database", services_database_stub)
    monkeypatch.setitem(sys.modules, "services.model_manager", services_model_manager_stub)
    monkeypatch.setitem(sys.modules, "api.auth", api_auth_stub)
    monkeypatch.setitem(sys.modules, "core", core_module)
    monkeypatch.setitem(sys.modules, "core.config", core_config_stub)

    models_module = importlib.import_module("api.models")

    custom_models_dir = tmp_path / "custom_models"
    monkeypatch.setenv("SEIDRA_MODELS_DIR", str(custom_models_dir))

    class DummySettings:
        @property
        def models_directory(self) -> Path:
            return Path(os.environ["SEIDRA_MODELS_DIR"]).expanduser().resolve()

    original_settings = models_module.settings
    models_module.settings = DummySettings()

    class DummyDatabaseService:
        def __init__(self) -> None:
            self.created_entries: list[dict[str, object]] = []
            self.updated_entries: list[tuple[str, dict[str, object]]] = []

        def get_lora_models(self):
            return []

        def update_lora_model(self, model_id: str, **data: object) -> None:
            self.updated_entries.append((model_id, data))

        def create_lora_model(self, **data: object) -> None:
            self.created_entries.append(data)

        def close(self) -> None:  # pragma: no cover - behaviour not asserted
            pass

    dummy_db = DummyDatabaseService()
    monkeypatch.setattr(models_module, "DatabaseService", lambda: dummy_db)

    models_module.download_model_task(
        model_id="test-model",
        download_url="https://example.com/model.safetensors",
        model_name="Test Model",
        category="style",
    )

    expected_dir = (custom_models_dir / "lora").resolve()
    expected_file = expected_dir / "test-model.safetensors"

    assert expected_dir.is_dir(), "LoRA directory should be created automatically"
    assert expected_file.exists(), "Downloaded model should be placed in the configured directory"

    assert dummy_db.created_entries, "Database entry should be created for new downloads"
    created_entry = dummy_db.created_entries[0]
    assert created_entry["file_path"] == str(expected_file)

    assert dummy_db.updated_entries, "File size should be updated after download"
    assert dummy_db.updated_entries[-1][0] == "test-model"
    assert dummy_db.updated_entries[-1][1]["file_size"] == expected_file.stat().st_size

    # Restore original settings for other tests.
    models_module.settings = original_settings
