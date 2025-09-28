from __future__ import annotations

from pathlib import Path

from core.config import Settings, ensure_runtime_directories
import pytest


@pytest.fixture()
def tmp_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        media_dir=tmp_path / "media",
        thumbnail_dir=tmp_path / "media" / "thumbs",
        models_dir=tmp_path / "models",
        temp_dir=tmp_path / "tmp",
    )


def test_ensure_runtime_directories_creates_all_paths(tmp_settings: Settings) -> None:
    ensure_runtime_directories(tmp_settings)

    assert tmp_settings.media_directory.exists()
    assert tmp_settings.thumbnail_directory.exists()
    assert tmp_settings.models_directory.exists()
    assert tmp_settings.tmp_directory.exists()


@pytest.mark.parametrize(
    "origins",
    [
        ["http://localhost:3000"],
        ["http://localhost:3000", "https://demo.seidra.ai"],
        [],
    ],
)
def test_allowed_origins_parsing(origins: list[str]) -> None:
    settings = Settings(_env_file=None, allowed_origins=origins)
    assert settings.allowed_origins == origins


def test_environment_variable_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEIDRA_ENV", raising=False)
    monkeypatch.delenv("SEIDRA_DEBUG", raising=False)
    monkeypatch.delenv("SEIDRA_DATABASE_URL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.database_url.endswith("seidra.db")


def test_tmp_directory_resolves_home(tmp_path: Path) -> None:
    configured_tmp = tmp_path / "home" / ".seidra" / "tmp"
    settings = Settings(_env_file=None, temp_dir=configured_tmp)
    ensure_runtime_directories(settings)
    assert configured_tmp.exists()
