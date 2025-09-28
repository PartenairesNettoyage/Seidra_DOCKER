from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.config import settings
import pytest
from services.database import DatabaseService
from services.generation_service import GenerationService


class StubModelManager:
    use_mock_pipeline = True

    async def initialize(self) -> None:  # pragma: no cover - simple stub
        return

    def get_last_generation_metrics(self, *, reset: bool = False) -> dict[str, Any] | None:
        return None

    def get_status_snapshot(self) -> dict[str, Any]:
        return {}

    def mark_unavailable(self, reason: str) -> None:  # pragma: no cover - stub
        return

    def mark_available(self) -> None:  # pragma: no cover - stub
        return


class StubWebSocketManager:
    async def send_generation_progress(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - stub
        return

    async def send_generation_complete(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - stub
        return

    async def send_generation_error(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - stub
        return

    async def dispatch_event(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - stub
        return


@pytest.mark.asyncio
async def test_emit_error_persists_without_service() -> None:
    service = GenerationService(
        model_manager=StubModelManager(),
        websocket_manager=StubWebSocketManager(),
        notification_service=None,
    )

    db = DatabaseService()
    try:
        _, total_before = db.list_notifications(limit=5)
    finally:
        db.close()

    await service._emit_notification(
        "error",
        "GPU failure",
        "Test persistence",
        category="system",
        metadata={"source": "unit-test"},
    )

    db = DatabaseService()
    try:
        items, total_after = db.list_notifications(limit=10)
        assert total_after == total_before + 1
        assert any(item.title == "GPU failure" for item in items)
    finally:
        db.delete_notifications_older_than(datetime.utcnow() + timedelta(days=1))
        db.close()


def test_purge_stale_notifications_removes_old_records() -> None:
    service = GenerationService(
        model_manager=StubModelManager(),
        websocket_manager=StubWebSocketManager(),
        notification_service=None,
    )

    old_retention = settings.notification_retention_days
    settings.notification_retention_days = 7

    db = DatabaseService()
    try:
        db.create_notification(
            level="error",
            title="Ancienne alerte",
            message="GPU hors service",
            category="system",
            metadata={"kind": "legacy"},
            tags=["test"],
            created_at=datetime.utcnow() - timedelta(days=10),
        )
        db.create_notification(
            level="warning",
            title="Notification récente",
            message="Queue chargée",
            category="system",
            metadata={"kind": "recent"},
            tags=["test"],
        )
    finally:
        db.close()

    try:
        service._purge_stale_notifications()
        db = DatabaseService()
        try:
            items, _ = db.list_notifications(limit=50)
            titles = {item.title for item in items}
            assert "Notification récente" in titles
            assert "Ancienne alerte" not in titles
        finally:
            db.delete_notifications_older_than(datetime.utcnow() + timedelta(days=1))
            db.close()
    finally:
        settings.notification_retention_days = old_retention
