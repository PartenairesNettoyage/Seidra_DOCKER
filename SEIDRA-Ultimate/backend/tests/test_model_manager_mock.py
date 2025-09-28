import importlib
import sys
import types
from typing import Any


def _ensure_pydantic_stack() -> None:
    """Provide lightweight fallbacks for ``pydantic`` and ``pydantic_settings`` if missing."""

    if "pydantic" not in sys.modules:
        module = types.ModuleType("pydantic")

        class _BaseModel:
            def __init__(self, **data: Any) -> None:
                for key, value in data.items():
                    setattr(self, key, value)

        def _field(default=None, *, default_factory=None, **_kwargs):  # noqa: ANN001
            if default_factory is not None:
                return default_factory()
            return default

        def _validator(*_args, **_kwargs):  # noqa: ANN001
            def decorator(func):
                return func

            return decorator

        module.BaseModel = _BaseModel
        module.Field = _field
        module.validator = _validator
        sys.modules["pydantic"] = module

    if "pydantic_settings" not in sys.modules:
        module = types.ModuleType("pydantic_settings")

        class _BaseSettings(sys.modules["pydantic"].BaseModel):  # type: ignore[attr-defined]
            model_config = {"extra": "allow"}

        module.BaseSettings = _BaseSettings
        sys.modules["pydantic_settings"] = module


def _ensure_httpx_stub() -> None:
    if "httpx" in sys.modules:
        return

    module = types.ModuleType("httpx")

    class AsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class Timeout:
        def __init__(self, *args, **kwargs):  # noqa: ANN001
            pass

    module.AsyncClient = AsyncClient
    module.Timeout = Timeout
    sys.modules["httpx"] = module


def _ensure_pil_stub() -> None:
    if "PIL" in sys.modules and "PIL.Image" in sys.modules:
        return

    pil_module = types.ModuleType("PIL")
    image_module = types.ModuleType("PIL.Image")

    class _Image:
        pass

    def _new(*_args, **_kwargs) -> _Image:  # noqa: ANN001
        return _Image()

    image_module.Image = _Image
    image_module.new = _new
    pil_module.Image = image_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = image_module


def test_model_manager_remote_status(tmp_path, monkeypatch) -> None:
    """ModelManager defaults to remote mode when CUDA pipelines are unavailable."""

    _ensure_pydantic_stack()
    _ensure_httpx_stub()
    _ensure_pil_stub()
    monkeypatch.setenv("SEIDRA_USE_REAL_MODELS", "0")

    from core import config

    importlib.reload(config)
    config.get_settings.cache_clear()
    config.settings = config.Settings(
        media_dir=tmp_path / "media",
        thumbnail_dir=tmp_path / "thumbnails",
        models_dir=tmp_path / "models",
        temp_dir=tmp_path / "tmp",
        comfyui_url="http://comfy.test",
        sadtalker_url="http://sadtalker.test",
    )

    from services import model_manager

    manager = model_manager.ModelManager()

    status: dict[str, Any] = manager.get_status_snapshot()

    assert status["mode"] == "remote"
    assert status["initialized"] is False
    assert status["current_model"] == "sdxl-base"
    assert isinstance(status["loras_loaded"], list)
    assert isinstance(status["last_update"], str)
