import importlib
from pathlib import Path
import sys
import types

import pytest


def _install_backend_stubs() -> None:
    """Install minimal modules required by the database layer."""

    alembic_module = types.ModuleType("alembic")
    alembic_command_module = types.ModuleType("alembic.command")

    def _noop_upgrade(*_args, **_kwargs):
        return None

    alembic_command_module.upgrade = _noop_upgrade
    alembic_module.command = alembic_command_module

    alembic_config_module = types.ModuleType("alembic.config")

    class _DummyConfig:
        def __init__(self, *_args, **_kwargs):
            self.options: dict[str, str] = {}

        def set_main_option(self, key: str, value: str) -> None:
            self.options[key] = value

    alembic_config_module.Config = _DummyConfig

    sys.modules.setdefault("alembic", alembic_module)
    sys.modules.setdefault("alembic.command", alembic_command_module)
    sys.modules.setdefault("alembic.config", alembic_config_module)

    core_config_module = types.ModuleType("core.config")
    core_config_module.settings = types.SimpleNamespace(
        database_url="sqlite:///:memory:",
        media_directory=Path("./data/media"),
        default_user_rotation_days=90,
    )

    sys.modules.setdefault("core.config", core_config_module)


_install_backend_stubs()

database = importlib.import_module("services.database")


@pytest.fixture(autouse=True)
def stub_hashing(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def fake_hash(password: str) -> str:
        calls.append(password)
        return f"hashed::{password}"

    monkeypatch.setattr(database, "_hash_password", fake_hash)
    return calls


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch):
    engine = database.create_engine("sqlite:///:memory:", echo=False, future=True)
    testing_session = database.sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", testing_session)

    database.Base.metadata.create_all(bind=engine)
    try:
        yield testing_session
    finally:
        database.Base.metadata.drop_all(bind=engine)


def test_insecure_default_password_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(database.DEFAULT_USER_PASSWORD_ENV, "demo")

    with pytest.raises(database.DefaultUserPasswordError):
        database.ensure_default_user_password_is_secure()


def test_default_user_disabled_when_password_missing(
    in_memory_db, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv(database.DEFAULT_USER_PASSWORD_ENV, raising=False)

    database.seed_default_user()

    with in_memory_db() as session:
        user = session.query(database.User).one()
        assert user.is_active is False


def test_default_user_password_rotation(
    in_memory_db, monkeypatch: pytest.MonkeyPatch, stub_hashing: list[str]
):
    monkeypatch.setenv(database.DEFAULT_USER_PASSWORD_ENV, "Sup3rSecurePassw0rd!")
    database.seed_default_user()

    with in_memory_db() as session:
        user = session.query(database.User).one()
        first_hash = user.hashed_password
        first_rotation = user.settings["security"]["default_user_last_rotation"]
        assert user.hashed_password == "hashed::Sup3rSecurePassw0rd!"
        assert user.is_active is True
        assert first_rotation is not None

    monkeypatch.setenv(database.DEFAULT_USER_PASSWORD_ENV, "An0ther-StrongSecret")
    database.seed_default_user()

    with in_memory_db() as session:
        user = session.query(database.User).one()
        assert user.hashed_password != first_hash
        assert user.hashed_password == "hashed::An0ther-StrongSecret"
        assert user.is_active is True
        second_rotation = user.settings["security"]["default_user_last_rotation"]
        assert second_rotation != first_rotation
    assert stub_hashing.count("Sup3rSecurePassw0rd!") == 1
    assert stub_hashing.count("An0ther-StrongSecret") == 1


def test_default_user_rotation_timestamp_preserved_when_password_unchanged(
    in_memory_db, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(database.DEFAULT_USER_PASSWORD_ENV, "SameSecret-123!")
    database.seed_default_user()
    first_rotation = database.get_default_user_last_rotation()

    database.seed_default_user()
    second_rotation = database.get_default_user_last_rotation()

    assert first_rotation is not None
    assert second_rotation == first_rotation
