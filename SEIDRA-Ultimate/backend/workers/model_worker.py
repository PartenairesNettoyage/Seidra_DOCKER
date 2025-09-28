"""Celery helpers that manage LoRA/model lifecycle operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from services.database import DatabaseService
from services.model_manager import ModelManager
from workers.celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(name="workers.model_worker.refresh_model_catalog")
def refresh_model_catalog() -> Dict[str, object]:
    manager = ModelManager()
    status = manager.get_status_snapshot()
    logger.info("Model catalog refreshed: %s", status.get("available_loras", []))
    return status


@celery_app.task(name="workers.model_worker.download_lora")
def download_lora(model_id: str) -> Dict[str, str]:
    manager = ModelManager()
    lora_config = manager.lora_models.get(model_id)
    if not lora_config:
        logger.warning("Unknown LoRA requested: %s", model_id)
        return {"status": "unknown", "model_id": model_id}

    path = Path(lora_config["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    db = DatabaseService()
    try:
        db.update_lora_model(model_id, file_path=str(path), is_downloaded=True)
    finally:
        db.close()

    logger.info("LoRA %s available at %s", model_id, path)
    return {"status": "downloaded", "model_id": model_id, "path": str(path)}
