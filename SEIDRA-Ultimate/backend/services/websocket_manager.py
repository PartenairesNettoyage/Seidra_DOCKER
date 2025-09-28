"""Realtime websocket management for SEIDRA Ultimate."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi import WebSocket


@dataclass
class ConnectionState:
    websocket: WebSocket
    user_id: Optional[int]
    channels: Set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)


class WebSocketManager:
    """Manage authenticated realtime connections and channel subscriptions."""

    def __init__(self) -> None:
        self.active_connections: Dict[str, ConnectionState] = {}
        self.user_connections: Dict[int, Set[str]] = defaultdict(set)
        self.channel_index: Dict[str, Set[str]] = defaultdict(set)
        self.default_channels: Set[str] = {"jobs", "system", "notifications"}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        *,
        user_id: Optional[int] = None,
        channels: Optional[Iterable[str]] = None,
    ) -> None:
        await websocket.accept()
        connection_channels = set(channels or self.default_channels)

        async with self._lock:
            state = ConnectionState(
                websocket=websocket,
                user_id=user_id,
                channels=connection_channels,
            )
            self.active_connections[client_id] = state
            if user_id is not None:
                self.user_connections[user_id].add(client_id)
            for channel in connection_channels:
                self.channel_index[channel].add(client_id)

        await self.send_personal_message(
            {
                "type": "connection",
                "message": "Connected to SEIDRA - Build your own myth",
                "clientId": client_id,
                "channels": sorted(connection_channels),
                "userId": user_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
            client_id,
        )

    def disconnect(self, client_id: str) -> None:
        state = self.active_connections.pop(client_id, None)
        if not state:
            return

        if state.user_id is not None:
            clients = self.user_connections.get(state.user_id)
            if clients:
                clients.discard(client_id)
                if not clients:
                    self.user_connections.pop(state.user_id, None)

        for channel in list(state.channels):
            subscribers = self.channel_index.get(channel)
            if subscribers:
                subscribers.discard(client_id)
                if not subscribers:
                    self.channel_index.pop(channel, None)

    async def send_personal_message(self, message: Dict[str, Any], client_id: str) -> None:
        state = self.active_connections.get(client_id)
        if not state:
            return
        try:
            await state.websocket.send_text(json.dumps(message))
        except Exception:
            self.disconnect(client_id)

    async def dispatch_event(
        self,
        message: Dict[str, Any],
        *,
        channels: Optional[Iterable[str]] = None,
        user_id: Optional[int] = None,
    ) -> None:
        recipients: Set[str] = set()
        target_channels = set(channels or [])

        if user_id is not None:
            for client_id in self.user_connections.get(user_id, set()):
                state = self.active_connections.get(client_id)
                if not state:
                    continue
                if not target_channels or state.channels.intersection(target_channels):
                    recipients.add(client_id)
        elif target_channels:
            for channel in target_channels:
                recipients.update(self.channel_index.get(channel, set()))
        else:
            recipients = set(self.active_connections.keys())

        for client_id in recipients:
            await self.send_personal_message(message, client_id)

    async def handle_client_message(self, client_id: str, payload: Dict[str, Any]) -> None:
        message_type = payload.get("type")
        state = self.active_connections.get(client_id)
        if not state:
            return

        state.last_seen = datetime.utcnow()

        if message_type == "subscribe":
            channels = set(payload.get("channels", []))
            if not channels:
                return
            await self._update_subscriptions(client_id, channels, add=True)
            await self.send_personal_message(
                {
                    "type": "subscription_ack",
                    "channels": sorted(self.active_connections[client_id].channels),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                client_id,
            )
        elif message_type == "unsubscribe":
            channels = set(payload.get("channels", []))
            if not channels:
                return
            await self._update_subscriptions(client_id, channels, add=False)
            await self.send_personal_message(
                {
                    "type": "subscription_ack",
                    "channels": sorted(self.active_connections[client_id].channels),
                    "timestamp": datetime.utcnow().isoformat(),
                },
                client_id,
            )
        elif message_type in {"ping", "heartbeat"}:
            await self.send_personal_message(
                {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                client_id,
            )
        else:
            await self.send_personal_message(
                {
                    "type": "error",
                    "message": f"Unknown command: {message_type}",
                    "timestamp": datetime.utcnow().isoformat(),
                },
                client_id,
            )

    async def _update_subscriptions(
        self, client_id: str, channels: Set[str], *, add: bool
    ) -> None:
        state = self.active_connections.get(client_id)
        if not state:
            return

        async with self._lock:
            if add:
                state.channels.update(channels)
                for channel in channels:
                    self.channel_index[channel].add(client_id)
            else:
                for channel in channels:
                    state.channels.discard(channel)
                    subscribers = self.channel_index.get(channel)
                    if subscribers:
                        subscribers.discard(client_id)
                        if not subscribers:
                            self.channel_index.pop(channel, None)

    async def send_generation_progress(
        self,
        job_id: str,
        progress: float,
        user_id: int,
        *,
        status: str = "processing",
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "type": "generation_progress",
            "jobId": job_id,
            "progress": progress,
            "status": status,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.dispatch_event(payload, channels={"jobs"}, user_id=user_id)

    async def send_generation_complete(
        self,
        job_id: str,
        result_files: List[str],
        user_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "type": "generation_complete",
            "jobId": job_id,
            "result": result_files,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.dispatch_event(payload, channels={"jobs"}, user_id=user_id)

    async def send_generation_error(
        self, job_id: str, error_message: str, user_id: int
    ) -> None:
        payload = {
            "type": "generation_error",
            "jobId": job_id,
            "error": error_message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.dispatch_event(payload, channels={"jobs"}, user_id=user_id)

    async def send_system_status(self, status_data: Dict[str, Any]) -> None:
        payload = {
            "type": "system_status",
            "data": status_data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.dispatch_event(payload, channels={"system"})

    def get_connection_stats(self) -> Dict[str, Any]:
        return {
            "total_connections": len(self.active_connections),
            "active_users": len(self.user_connections),
            "channels": {channel: len(clients) for channel, clients in self.channel_index.items()},
            "clients": [
                {
                    "clientId": client_id,
                    "userId": state.user_id,
                    "channels": sorted(state.channels),
                    "connectedAt": state.connected_at.isoformat(),
                    "lastSeen": state.last_seen.isoformat(),
                }
                for client_id, state in self.active_connections.items()
            ],
        }


__all__ = ["WebSocketManager"]

