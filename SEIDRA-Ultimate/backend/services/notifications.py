"""Notification routing utilities for SEIDRA Ultimate."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from itertools import islice
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence

from core.config import (
    PagerDutyNotificationSettings,
    Settings,
    SlackNotificationSettings,
    settings as global_settings,
)
from services.database import DatabaseService


LOGGER = logging.getLogger("seidra.notifications")

_SLACK_LEVEL_COLORS: Dict[str, str] = {
    "critical": "#dc2626",
    "error": "#f97316",
    "warning": "#fbbf24",
    "info": "#0ea5e9",
    "success": "#22c55e",
}

_PAGERDUTY_SEVERITIES: Dict[str, str] = {
    "critical": "critical",
    "error": "error",
    "warning": "warning",
    "info": "info",
}


class NotificationService:
    """Centralise l'écriture, le cache et la diffusion des notifications."""

    def __init__(
        self,
        *,
        websocket_manager: Optional["WebSocketManager"] = None,
        history_size: int = 200,
        preload: bool = True,
        app_settings: Optional[Settings] = None,
        slack_config: Optional[SlackNotificationSettings] = None,
        pagerduty_config: Optional[PagerDutyNotificationSettings] = None,
        http_client_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        from services.websocket_manager import WebSocketManager  # Local import pour éviter les cycles

        capacity = max(history_size, 1)
        self.websocket_manager: Optional[WebSocketManager] = websocket_manager
        self._history: Deque[Dict[str, Any]] = deque(maxlen=capacity)
        self._lock = asyncio.Lock()
        self._app_settings: Settings = app_settings or global_settings
        self._slack_config = slack_config or getattr(
            self._app_settings, "notifications_slack", SlackNotificationSettings()
        )
        self._pagerduty_config = pagerduty_config or getattr(
            self._app_settings, "notifications_pagerduty", PagerDutyNotificationSettings()
        )
        self._http_client_factory = http_client_factory

        if preload:
            self._preload_history(capacity)

    def attach_websocket_manager(self, manager: "WebSocketManager") -> None:
        """Attach or swap the websocket manager at runtime."""

        self.websocket_manager = manager

    async def push(
        self,
        level: str,
        title: str,
        message: str,
        *,
        category: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        """Record a notification and broadcast it to subscribers."""

        entry = await asyncio.to_thread(
            self._store_notification,
            level,
            title,
            message,
            category,
            metadata or {},
            list(tags or []),
        )

        async with self._lock:
            self._history.appendleft(entry)

        if self.websocket_manager:
            await self.websocket_manager.dispatch_event(
                {"type": "notification", **entry}, channels={"notifications"}
            )

        await self._dispatch_external(entry)

        return entry

    async def list_notifications(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Retourne l'historique paginé des notifications persistées."""

        result = await asyncio.to_thread(self._fetch_notifications, limit, offset)
        return result

    def list_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the latest notifications up to ``limit`` entries."""

        return list(islice(self._history, 0, max(limit, 0)))

    # --- Persistence helpers -------------------------------------------

    def _preload_history(self, limit: int) -> None:
        try:
            result = self._fetch_notifications(limit, 0)
        except Exception:
            return

        items = result.get("items", [])
        for entry in reversed(items):
            self._history.appendleft(entry)
        return

    def _store_notification(
        self,
        level: str,
        title: str,
        message: str,
        category: str,
        metadata: Dict[str, Any],
        tags: List[str],
    ) -> Dict[str, Any]:
        db = DatabaseService()
        try:
            record = db.create_notification(
                level=level,
                title=title,
                message=message,
                category=category,
                metadata=metadata,
                tags=tags,
            )
            return db.serialize_notification(record)
        finally:
            db.close()

    def _fetch_notifications(self, limit: int, offset: int) -> Dict[str, Any]:
        db = DatabaseService()
        try:
            items, total = db.list_notifications(limit=max(limit, 0), offset=max(offset, 0))
            serialized = [db.serialize_notification(item) for item in items]
            return {
                "items": serialized,
                "total": total,
                "limit": max(limit, 0),
                "offset": max(offset, 0),
                "hasMore": max(offset, 0) + len(serialized) < total,
            }
        finally:
            db.close()

    async def _dispatch_external(self, entry: Dict[str, Any]) -> None:
        tasks = []
        if self._slack_config.enabled and self._slack_config.webhook_url:
            tasks.append(self._send_to_slack(entry))
        if self._pagerduty_config.enabled and self._pagerduty_config.routing_key:
            tasks.append(self._send_to_pagerduty(entry))
        if tasks:
            await asyncio.gather(*tasks)

    @staticmethod
    def _should_forward(level: str, allowed_levels: Sequence[str]) -> bool:
        if not allowed_levels:
            return True
        return level.lower() in {item.lower() for item in allowed_levels}

    def _slack_color(self, level: str) -> str:
        return _SLACK_LEVEL_COLORS.get(level.lower(), "#64748b")

    def _format_slack_payload(
        self, entry: Dict[str, Any], config: SlackNotificationSettings
    ) -> Dict[str, Any]:
        level = entry.get("level", "info").lower()
        title = entry.get("title", "")
        message = entry.get("message", "")
        text = f"[{level.upper()}] {title}: {message}".strip()

        payload: Dict[str, Any] = {"text": text}
        if config.username:
            payload["username"] = config.username
        if config.icon_emoji:
            payload["icon_emoji"] = config.icon_emoji

        fields: List[Dict[str, Any]] = []
        category = entry.get("category")
        if category:
            fields.append({"title": "Catégorie", "value": str(category), "short": True})
        tags = entry.get("tags") or []
        if tags:
            fields.append({"title": "Tags", "value": ", ".join(tags), "short": True})
        metadata = entry.get("metadata") or {}
        if metadata:
            pretty = json.dumps(metadata, ensure_ascii=False, indent=2)
            fields.append({"title": "Métadonnées", "value": f"```\n{pretty}\n```", "short": False})

        attachment: Dict[str, Any] = {"color": self._slack_color(level)}
        if fields:
            attachment["fields"] = fields
        timestamp = entry.get("timestamp")
        if timestamp:
            attachment["footer"] = timestamp

        if fields or timestamp:
            payload["attachments"] = [attachment]

        return payload

    async def _send_to_slack(self, entry: Dict[str, Any]) -> None:
        config = self._slack_config
        level = entry.get("level", "info")
        if not self._should_forward(level, config.levels):
            return

        payload = self._format_slack_payload(entry, config)
        await self._post_json(config.webhook_url or "", payload)

    def _pagerduty_severity(self, level: str) -> str:
        return _PAGERDUTY_SEVERITIES.get(level.lower(), "info")

    def _build_dedup_key(self, entry: Dict[str, Any]) -> Optional[str]:
        prefix = self._pagerduty_config.dedup_key_prefix
        identifier = entry.get("id")
        if identifier is None and not prefix:
            return None
        identifier_str = str(identifier) if identifier is not None else ""
        if prefix:
            return f"{prefix}{identifier_str}" if identifier_str else prefix
        return identifier_str or None

    async def _send_to_pagerduty(self, entry: Dict[str, Any]) -> None:
        config = self._pagerduty_config
        level = entry.get("level", "info")
        if not self._should_forward(level, config.levels):
            return

        payload: Dict[str, Any] = {
            "routing_key": config.routing_key,
            "event_action": "trigger",
            "client": config.client,
            "payload": {
                "summary": f"[{level.upper()}] {entry.get('title', '')}".strip(),
                "severity": self._pagerduty_severity(level),
                "source": config.source,
                "component": entry.get("category", "seidra"),
                "custom_details": {
                    "message": entry.get("message"),
                    "metadata": entry.get("metadata") or {},
                    "tags": entry.get("tags") or [],
                },
            },
        }

        timestamp = entry.get("timestamp")
        if timestamp:
            payload["payload"]["timestamp"] = timestamp

        dedup_key = self._build_dedup_key(entry)
        if dedup_key:
            payload["dedup_key"] = dedup_key

        headers = {"Content-Type": "application/json"}
        await self._post_json(config.api_url, payload, headers=headers)

    async def _post_json(
        self, url: str, payload: Dict[str, Any], *, headers: Optional[Dict[str, str]] = None
    ) -> None:
        if not url:
            return

        try:
            import httpx
        except ImportError:  # pragma: no cover - dépend de l'environnement d'exécution
            LOGGER.warning(
                "Le module httpx est requis pour envoyer les notifications externes."
            )
            return

        client: Any
        close_client = False
        if self._http_client_factory:
            client = self._http_client_factory()
            close_client = True
        else:
            timeout = httpx.Timeout(10.0, connect=5.0, read=10.0)
            client = httpx.AsyncClient(timeout=timeout)
            close_client = True

        try:
            response = await client.post(url, json=payload, headers=headers)
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
        except Exception:  # pragma: no cover - best-effort
            LOGGER.exception("Échec de l'envoi de la notification vers %s", url)
        finally:
            if close_client and hasattr(client, "aclose"):
                await client.aclose()


__all__ = ["NotificationService"]

