import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .test_model_manager_mock import (
    _ensure_httpx_stub,
    _ensure_pil_stub,
    _ensure_pydantic_stack,
)


class _StubImage:
    def __init__(self, payload: bytes = b"stub") -> None:
        self._payload = payload

    def save(self, destination: Path) -> None:  # pragma: no cover - IO helper
        destination.write_bytes(self._payload)


class _StubPipeline:
    def __call__(self, *args: Any, **kwargs: Any) -> SimpleNamespace:  # noqa: ANN401
        return SimpleNamespace(images=[_StubImage()])


def test_model_manager_initial_mode(tmp_path, monkeypatch) -> None:
    """ModelManager initializes without monkeypatch and reports coherent mode."""

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

    importlib.reload(model_manager)
    manager = model_manager.ModelManager()

    expected_mode = "remote" if manager.remote_inference else (
        "mock" if manager.use_mock_pipeline else "cuda"
    )

    status = manager.get_status_snapshot()

    assert manager.use_mock_pipeline in {True, False}
    assert status["mode"] == expected_mode
    assert status["initialized"] is False


def test_generate_image_metrics_local(tmp_path, monkeypatch) -> None:
    """Local image generation should populate metrics without NameError."""

    _ensure_pydantic_stack()
    _ensure_httpx_stub()
    _ensure_pil_stub()

    monkeypatch.setenv("SEIDRA_USE_REAL_MODELS", "1")

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

    importlib.reload(model_manager)

    manager = model_manager.ModelManager()
    manager.remote_inference = False
    manager.use_mock_pipeline = False
    manager.base_pipeline = _StubPipeline()

    outputs: list[str] = asyncio.run(
        manager.generate_image(
            prompt="test prompt",
            negative_prompt="",
            width=32,
            height=32,
            num_inference_steps=2,
            guidance_scale=5.0,
        )
    )

    assert outputs
    for path in outputs:
        assert Path(path).exists()

    metrics = manager.get_last_generation_metrics()
    assert metrics is not None
    assert metrics["media_type"] == "image"
    assert metrics["model_name"] == "sdxl-base"
    assert metrics["outputs"] == len(outputs)
    assert metrics["extra"]["implementation"] == "diffusers"
    assert metrics["extra"]["width"] == 32

