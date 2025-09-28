"""Utilitaires pour la mise en file d'attente locale des tâches Celery.

Ce module fournit une file d'attente persistante très légère permettant de
retenir temporairement les tâches lorsque le broker Celery est indisponible.
Les entrées sont stockées dans le répertoire temporaire de l'application et
rejouées dès que la publication redevient possible.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.config import settings


@dataclass
class LocalQueueEntry:
    """Représente une tâche en attente de republication."""

    task_name: str
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    queue: Optional[str] = None
    priority: Optional[int] = None
    countdown: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    enqueued_at: float = field(default_factory=lambda: time.time())
    ready_at: Optional[float] = None
    attempts: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_name": self.task_name,
            "args": self.args,
            "kwargs": self.kwargs,
            "queue": self.queue,
            "priority": self.priority,
            "countdown": self.countdown,
            "metadata": self.metadata,
            "enqueued_at": self.enqueued_at,
            "ready_at": self.ready_at,
            "attempts": self.attempts,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LocalQueueEntry":
        return cls(
            task_name=payload.get("task_name", ""),
            args=list(payload.get("args", [])),
            kwargs=dict(payload.get("kwargs", {})),
            queue=payload.get("queue"),
            priority=payload.get("priority"),
            countdown=payload.get("countdown"),
            metadata=dict(payload.get("metadata", {})),
            enqueued_at=float(payload.get("enqueued_at", time.time())),
            ready_at=payload.get("ready_at"),
            attempts=int(payload.get("attempts", 0) or 0),
            last_error=payload.get("last_error"),
        )


class LocalRetryQueue:
    """Gestionnaire de file d'attente persistante pour les tâches Celery."""

    def __init__(
        self,
        name: str,
        *,
        max_size: int = 500,
        storage_dir: Optional[Path] = None,
    ) -> None:
        self.name = name
        directory = storage_dir or settings.tmp_directory
        directory.mkdir(parents=True, exist_ok=True)
        self._path = directory / f"{name}_tasks.json"
        self._lock = threading.Lock()
        self._max_size = max(10, max_size)

    # ----- helpers internes -------------------------------------------------
    def _load_entries(self) -> List[LocalQueueEntry]:
        if not self._path.exists():
            return []
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return []
        entries: List[LocalQueueEntry] = []
        for item in payload if isinstance(payload, list) else []:
            try:
                entries.append(LocalQueueEntry.from_dict(item))
            except Exception:
                continue
        return entries

    def _write_entries(self, entries: Iterable[LocalQueueEntry]) -> None:
        serialized = [entry.to_dict() for entry in entries]
        if not serialized:
            if self._path.exists():
                self._path.unlink(missing_ok=True)
            return
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(serialized), encoding="utf-8")
        tmp_path.replace(self._path)

    # ----- API publique ----------------------------------------------------
    def enqueue(
        self,
        *,
        task_name: str,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        queue: Optional[str] = None,
        priority: Optional[int] = None,
        countdown: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> LocalQueueEntry:
        """Ajoute une tâche à la file locale."""

        entry = LocalQueueEntry(
            task_name=task_name,
            args=list(args or []),
            kwargs=dict(kwargs or {}),
            queue=queue,
            priority=priority,
            countdown=countdown,
            metadata=dict(metadata or {}),
            ready_at=(time.time() + countdown) if countdown else None,
            last_error=error,
        )
        with self._lock:
            entries = self._load_entries()
            entries.append(entry)
            if len(entries) > self._max_size:
                # On conserve les entrées les plus récentes
                entries = entries[-self._max_size :]
            self._write_entries(entries)
        return entry

    def drain(
        self,
        dispatcher: Callable[[LocalQueueEntry], bool],
        *,
        max_items: Optional[int] = None,
    ) -> Dict[str, int]:
        """Tente de republier les tâches en attente."""

        dispatched = 0
        remaining_entries: List[LocalQueueEntry] = []

        with self._lock:
            entries = self._load_entries()

        limit = max_items if max_items is not None else len(entries)
        now = time.time()

        for index, entry in enumerate(entries):
            if index >= limit:
                remaining_entries.extend(entries[index:])
                break
            if entry.ready_at and entry.ready_at > now:
                remaining_entries.append(entry)
                continue
            try:
                success = dispatcher(entry)
            except Exception as exc:  # pragma: no cover - enregistre l'erreur
                entry.attempts += 1
                entry.last_error = str(exc)
                remaining_entries.append(entry)
            else:
                if success:
                    dispatched += 1
                else:
                    entry.attempts += 1
                    remaining_entries.append(entry)

        if remaining_entries:
            with self._lock:
                self._write_entries(remaining_entries)
        else:
            with self._lock:
                self._write_entries([])

        return {"dispatched": dispatched, "remaining": len(remaining_entries)}

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            entries = self._load_entries()
        if not entries:
            return {"size": 0, "oldest": None, "newest": None}
        return {
            "size": len(entries),
            "oldest": entries[0].enqueued_at,
            "newest": entries[-1].enqueued_at,
        }


    def __len__(self) -> int:
        return int(self.stats().get("size", 0))


_QUEUES: Dict[str, LocalRetryQueue] = {}
_QUEUES_LOCK = threading.Lock()


def get_local_queue(name: str) -> LocalRetryQueue:
    with _QUEUES_LOCK:
        if name not in _QUEUES:
            _QUEUES[name] = LocalRetryQueue(name)
        return _QUEUES[name]


def publish_task_with_local_fallback(
    task: Any,
    *,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    queue: Optional[str] = None,
    priority: Optional[int] = None,
    countdown: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
    local_queue: Optional[LocalRetryQueue] = None,
    max_attempts: int = 3,
    backoff: float = 1.5,
    retry_policy: Optional[Dict[str, Any]] = None,
) -> bool:
    """Publie une tâche Celery avec répétitions et repli local."""

    if task is None:
        raise ValueError("La tâche Celery fournie est invalide")

    args = list(args or [])
    kwargs = dict(kwargs or {})
    options: Dict[str, Any] = {}
    if queue is not None:
        options["queue"] = queue
    if priority is not None:
        options["priority"] = priority
    if countdown:
        options["countdown"] = countdown

    if retry_policy:
        options["retry"] = True
        options["retry_policy"] = retry_policy
    else:
        options.setdefault("retry", True)

    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            task.apply_async(args=args, kwargs=kwargs, **options)
            return True
        except Exception as exc:  # pragma: no cover - dépend du broker
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(min(backoff * attempt, 5.0))

    queue_ref = local_queue or get_local_queue(task.name.replace(".", "_"))
    queue_ref.enqueue(
        task_name=task.name,
        args=args,
        kwargs=kwargs,
        queue=queue,
        priority=priority,
        countdown=countdown,
        metadata=metadata,
        error=str(last_error) if last_error else None,
    )
    return False
