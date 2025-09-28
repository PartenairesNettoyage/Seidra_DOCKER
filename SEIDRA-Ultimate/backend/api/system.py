"""System telemetry and runtime information endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends

from api.auth import verify_token
from core.config import settings
from services.gpu_monitor import GPUMonitor
from services.model_manager import ModelManager
from services.notifications import NotificationService
from services.telemetry_service import TelemetryService

router = APIRouter()

_gpu_monitor: Optional[GPUMonitor] = None
_model_manager: Optional[ModelManager] = None
_telemetry_service: Optional[TelemetryService] = None
_notification_service: Optional[NotificationService] = None


def set_gpu_monitor(monitor: GPUMonitor) -> None:
    global _gpu_monitor
    _gpu_monitor = monitor


def set_model_manager(manager: ModelManager) -> None:
    global _model_manager
    _model_manager = manager


def set_telemetry_service(service: TelemetryService) -> None:
    global _telemetry_service
    _telemetry_service = service


def set_notification_service(service: NotificationService) -> None:
    global _notification_service
    _notification_service = service


@router.get("/info")
async def system_info(_current_user=Depends(verify_token)) -> Dict[str, Any]:
    telemetry_snapshot: Optional[Dict[str, Any]] = None
    if _telemetry_service:
        telemetry_snapshot = await _telemetry_service.get_snapshot()

    if telemetry_snapshot:
        gpu_status = telemetry_snapshot.get("gpu", {"gpu_available": False})
    else:
        gpu_status = await _gpu_monitor.get_status() if _gpu_monitor else {"gpu_available": False}

    model_inventory: List[Dict[str, Any]] = []
    if _model_manager:
        for name, model in _model_manager.loaded_models.items():
            model_inventory.append(
                {
                    "name": name,
                    "description": getattr(model, "description", ""),
                    "is_loaded": True,
                }
            )
            
    model_info = telemetry_snapshot.get("models") if telemetry_snapshot else {}
    notification_preview = []
    if _notification_service:
        notification_preview = _notification_service.list_recent(limit=5)
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "debug": settings.debug,
        "gpu": gpu_status,
        "models": model_inventory,
        "model_info": model_info,
        "connections": telemetry_snapshot.get("connections", {}) if telemetry_snapshot else {},
        "system": telemetry_snapshot.get("system", {}) if telemetry_snapshot else {},
        "media_directory": str(settings.media_directory),
        "notifications": notification_preview,
    }


@router.get("/telemetry")
async def telemetry(minutes: int = 10, _current_user=Depends(verify_token)) -> Dict[str, Any]:
    telemetry_snapshot: Dict[str, Any] = {}
    if _telemetry_service:
        telemetry_snapshot = await _telemetry_service.get_snapshot()

    gpu_history = []
    if _telemetry_service:
        gpu_history = await _telemetry_service.get_gpu_history(minutes=minutes)
    elif _gpu_monitor:
        gpu_history = await _gpu_monitor.get_history(minutes=minutes)

    if not telemetry_snapshot:
        telemetry_snapshot = {
            "gpu": await _gpu_monitor.get_status() if _gpu_monitor else {"gpu_available": False}
        }

    performance = telemetry_snapshot.get("gpuPerformance")
    if not performance and _gpu_monitor:
        performance = await _gpu_monitor.get_performance_metrics()

    aggregate_history = (
        _telemetry_service.get_history_snapshots(minutes)
        if _telemetry_service
        else []
    )

    generation_data = telemetry_snapshot.get("generation", {}) if telemetry_snapshot else {}

    return {
        "snapshot": telemetry_snapshot,
        "gpuHistory": gpu_history,
        "gpuPerformance": performance,
        "aggregatedSnapshots": aggregate_history,
        "generation": generation_data,
        "recentGeneration": generation_data.get("recent", []),
    }


@router.get("/telemetry/generation")
async def generation_telemetry(
    limit: int = 50,
    minutes: Optional[int] = None,
    media_type: Optional[str] = None,
    _current_user=Depends(verify_token),
) -> Dict[str, Any]:
    if not _telemetry_service:
        return {"items": [], "summary": {}, "recent": []}
    return await _telemetry_service.get_generation_metrics(
        limit=limit, minutes=minutes, media_type=media_type
    )


@router.get("/notifications")
async def list_notifications(
    limit: int = 20,
    offset: int = 0,
    _current_user=Depends(verify_token),
) -> Dict[str, Any]:
    if not _notification_service:
        return {"items": [], "total": 0, "limit": limit, "offset": offset, "hasMore": False}
    return await _notification_service.list_notifications(limit=limit, offset=offset)
