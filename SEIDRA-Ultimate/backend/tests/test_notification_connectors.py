from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest
from sqlalchemy.exc import OperationalError

TEST_DB_PATH = Path("test-notifications.db")
os.environ.setdefault("SEIDRA_DATABASE_URL", f"sqlite:///{TEST_DB_PATH}")

from core.config import PagerDutyNotificationSettings, SlackNotificationSettings
from services.database import DatabaseService
from services.notifications import NotificationService


class _StubResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _StubAsyncClient:
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []

    async def post(
        self,
        url: str,
        *,
        json: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
    ) -> _StubResponse:
        self.requests.append({"url": url, "json": json or {}, "headers": headers or {}})
        return _StubResponse()

    async def aclose(self) -> None:  # pragma: no cover - noop for stub
        return


class _ClientFactory:
    def __init__(self) -> None:
        self.clients: List[_StubAsyncClient] = []

    def __call__(self) -> _StubAsyncClient:
        client = _StubAsyncClient()
        self.clients.append(client)
        return client


@pytest.fixture
def client_factory() -> _ClientFactory:
    return _ClientFactory()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _cleanup_notifications() -> None:
    yield
    db = DatabaseService()
    try:
        db.delete_notifications_older_than(datetime.utcnow() + timedelta(days=1))
    except OperationalError:
        pass
    finally:
        db.close()


@pytest.mark.anyio("asyncio")
async def test_slack_connector_dispatches_payload(client_factory: _ClientFactory) -> None:
    service = NotificationService(
        websocket_manager=None,
        preload=False,
        slack_config=SlackNotificationSettings(
            enabled=True,
            webhook_url="https://hooks.slack.test/demo",
            levels=["error", "critical"],
            username="SEIDRA Bot",
            icon_emoji=":rocket:",
        ),
        pagerduty_config=PagerDutyNotificationSettings(enabled=False),
        http_client_factory=client_factory,
    )

    await service.push(
        "error",
        "GPU offline",
        "Unit test payload",
        category="system",
        metadata={"node": "gpu-01"},
        tags=["gpu", "critical"],
    )

    assert client_factory.clients, "Le connecteur Slack devrait effectuer un appel HTTP"
    last_request = client_factory.clients[-1].requests[-1]
    assert last_request["url"] == "https://hooks.slack.test/demo"
    body = last_request["json"]
    assert "[ERROR]" in body["text"]
    assert body.get("username") == "SEIDRA Bot"
    assert body.get("icon_emoji") == ":rocket:"
    assert body.get("attachments"), "Les métadonnées doivent être incluses dans la charge Slack"


@pytest.mark.anyio("asyncio")
async def test_slack_connector_respects_level_filter(client_factory: _ClientFactory) -> None:
    service = NotificationService(
        websocket_manager=None,
        preload=False,
        slack_config=SlackNotificationSettings(
            enabled=True,
            webhook_url="https://hooks.slack.test/demo",
            levels=["critical"],
        ),
        pagerduty_config=PagerDutyNotificationSettings(enabled=False),
        http_client_factory=client_factory,
    )

    await service.push(
        "warning",
        "Queue longue",
        "Notification de test",
        category="system",
    )

    assert not client_factory.clients, "Aucun appel ne doit être effectué pour un niveau filtré"


@pytest.mark.anyio("asyncio")
async def test_pagerduty_connector_enqueues_event(client_factory: _ClientFactory) -> None:
    service = NotificationService(
        websocket_manager=None,
        preload=False,
        slack_config=SlackNotificationSettings(enabled=False),
        pagerduty_config=PagerDutyNotificationSettings(
            enabled=True,
            routing_key="routing-key",
            levels=["error", "critical"],
            source="seidra-ci",
            client="SEIDRA Ultimate",
            dedup_key_prefix="seidra-test-",
        ),
        http_client_factory=client_factory,
    )

    entry = await service.push(
        "critical",
        "GPU offline",
        "Incident critique",
        category="system",
        metadata={"node": "gpu-01"},
        tags=["gpu"],
    )

    assert client_factory.clients, "Le connecteur PagerDuty devrait effectuer un appel HTTP"
    request = client_factory.clients[-1].requests[-1]
    assert request["url"] == "https://events.pagerduty.com/v2/enqueue"
    body = request["json"]
    assert body["routing_key"] == "routing-key"
    assert body["payload"]["severity"] == "critical"
    assert body["payload"]["source"] == "seidra-ci"
    assert body["payload"]["custom_details"]["metadata"]["node"] == "gpu-01"
    assert body.get("dedup_key", "").startswith("seidra-test-")
    assert str(entry["id"]) in body.get("dedup_key", "")
