"""
SEIDRA Database Service
SQLite with SQLAlchemy ORM
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple

try:  # pragma: no cover - Alembic optionnel pour certains tests
    from alembic import command
    from alembic.config import Config as AlembicConfig
except ImportError:  # pragma: no cover - environnement minimal sans Alembic
    command = None  # type: ignore[assignment]
    AlembicConfig = None  # type: ignore[assignment]
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from core.config import secret_manager, settings
from api.settings_models import DEFAULT_SETTINGS

DATABASE_URL = settings.database_url
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_SCHEMA_INITIALISED = False


def ensure_schema() -> None:
    """Create database tables on first access if they do not exist."""

    global _SCHEMA_INITIALISED
    if _SCHEMA_INITIALISED:
        return

    Base.metadata.create_all(bind=engine)
    _SCHEMA_INITIALISED = True

ALEMBIC_CONFIG_PATH = Path(__file__).resolve().parent.parent / "alembic.ini"
_ACTIVE_MODULE_ALIAS = "seidra._active_database_module"
sys.modules[_ACTIVE_MODULE_ALIAS] = sys.modules[__name__]


def _configure_alembic() -> AlembicConfig:
    if AlembicConfig is None:  # pragma: no cover - alembic absent
        raise RuntimeError("Alembic n'est pas disponible dans cet environnement")
    config = AlembicConfig(str(ALEMBIC_CONFIG_PATH))
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def run_migrations() -> None:
    """Upgrade the database schema to the latest Alembic revision."""

    if command is None:  # pragma: no cover - alembic absent
        raise RuntimeError("Impossible d'exécuter les migrations Alembic: module indisponible")

    command.upgrade(_configure_alembic(), "head")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_nsfw_enabled = Column(Boolean, default=False)
    age_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    settings = Column(SQLiteJSON, default={})


class Persona(Base):
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    style_prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text, default="")
    lora_models = Column(SQLiteJSON, default=[])
    generation_params = Column(SQLiteJSON, default={})
    avatar_url = Column(String(500))
    tags = Column(SQLiteJSON, default=[])
    is_favorite = Column(Boolean, default=False)
    is_nsfw = Column(Boolean, default=False)
    metadata_payload = Column("metadata", SQLiteJSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True)
    job_type = Column(String(50), default="image")
    prompt = Column(Text, nullable=False)
    negative_prompt = Column(Text, default="")
    model_name = Column(String(100), nullable=False)
    lora_models = Column(SQLiteJSON, default=[])
    parameters = Column(SQLiteJSON, nullable=False)
    status = Column(String(20), default="pending", index=True)
    progress = Column(Float, default=0.0)
    result_images = Column(SQLiteJSON, default=[])
    metadata_payload = Column("metadata", SQLiteJSON, default={})
    is_nsfw = Column(Boolean, default=False)
    nsfw_score = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class LoRAModel(Base):
    __tablename__ = "lora_models"

    id = Column(String(100), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    file_path = Column(String(500), nullable=False)
    download_url = Column(String(500))
    category = Column(String(50), index=True)
    tags = Column(SQLiteJSON, default=[])
    is_downloaded = Column(Boolean, default=False)
    file_size = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class MediaItem(Base):
    __tablename__ = "media_items"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    job_id = Column(String(36), ForeignKey("generation_jobs.id"), index=True, nullable=False)
    file_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500))
    file_type = Column(String(50), default="image")
    mime_type = Column(String(100), default="image/png")
    metadata_payload = Column("metadata", SQLiteJSON, default={})
    tags = Column(SQLiteJSON, default=[])
    is_favorite = Column(Boolean, default=False)
    is_nsfw = Column(Boolean, default=False)
    nsfw_tags = Column(SQLiteJSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NSFWSettings(Base):
    __tablename__ = "nsfw_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    enabled = Column(Boolean, default=True)
    age_verified = Column(Boolean, default=False)
    intensity = Column(String(20), default="medium")
    categories = Column(SQLiteJSON, default={})
    overrides = Column(SQLiteJSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GenerationMetric(Base):
    __tablename__ = "generation_metrics"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), ForeignKey("generation_jobs.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)
    media_type = Column(String(50), default="image", nullable=False, index=True)
    model_name = Column(String(100), nullable=True)
    prompt = Column(Text, nullable=True)
    outputs = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    throughput = Column(Float, nullable=True)
    vram_allocated_mb = Column(Float, nullable=True)
    vram_reserved_mb = Column(Float, nullable=True)
    vram_peak_mb = Column(Float, nullable=True)
    vram_delta_mb = Column(Float, nullable=True)
    extra = Column(SQLiteJSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow, index=True)



class VideoTimeline(Base):
    __tablename__ = "video_timelines"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    frame_rate = Column(Integer, default=24)
    total_duration = Column(Float, default=0.0)
    timeline_payload = Column("timeline", SQLiteJSON, default={})
    job_id = Column(String(36), ForeignKey("generation_jobs.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, index=True)
    level = Column(String(20), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False, default="")
    category = Column(String(50), nullable=False, default="system", index=True)
    metadata_payload = Column("metadata", SQLiteJSON, default={})
    tags = Column(SQLiteJSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow, index=True)



DEFAULT_USER_PASSWORD_ENV = "SEIDRA_DEFAULT_USER_PASSWORD"
DEFAULT_USER_MIN_LENGTH = 12
DEFAULT_USER_FORBIDDEN_PASSWORDS = {"demo", "password", "changeme"}


class DefaultUserPasswordError(RuntimeError):
    """Raised when the default user password is considered insecure."""


DEFAULT_USER_TEMPLATE = {
    "id": 1,
    "username": "demo",
    "email": "demo@seidra.ai",
    "is_active": True,
    "is_nsfw_enabled": True,
    "age_verified": True,
    "settings": {
        "theme": "ultimate",
        "language": "en",
        "notifications": {
            "web": True,
            "email": False,
            "slack": False,
        },
        "telemetry_opt_in": True,
    },
}

DEFAULT_NSFW_SETTINGS = {
    "user_id": None,
    "enabled": True,
    "age_verified": True,
    "intensity": "medium",
    "categories": {
        "suggestive": True,
        "explicit": False,
        "violence": False,
    },
    "overrides": {},
}


@contextmanager
def session_scope() -> Iterable[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ensure_default_user_password_is_secure() -> Optional[str]:
    """Validate the default user password from the environment.

    Returns the password when present and considered secure.  A secure password
    must have a minimum length and cannot match a list of forbidden values.  If
    the password is missing, ``None`` is returned which signals that the default
    account should be disabled.  When the password is insecure a
    :class:`DefaultUserPasswordError` is raised to stop the initialisation.
    """

    raw_password = secret_manager.get(DEFAULT_USER_PASSWORD_ENV)
    if raw_password is None:
        return None

    if not isinstance(raw_password, str):
        raise DefaultUserPasswordError(
            f"Le secret {DEFAULT_USER_PASSWORD_ENV} doit être une chaîne de caractères."
        )
    if not raw_password.strip():
        return None

    candidate = raw_password.strip()
    if len(candidate) < DEFAULT_USER_MIN_LENGTH:
        raise DefaultUserPasswordError(
            "SEIDRA_DEFAULT_USER_PASSWORD must contain at least "
            f"{DEFAULT_USER_MIN_LENGTH} characters."
        )

    if candidate.lower() in DEFAULT_USER_FORBIDDEN_PASSWORDS:
        raise DefaultUserPasswordError(
            "SEIDRA_DEFAULT_USER_PASSWORD uses a forbidden default value."
        )

    return candidate


def _hash_password(password: str) -> str:
    from api.auth import get_password_hash

    return get_password_hash(password)


def _update_default_user_rotation_settings(
    settings: Optional[Dict[str, Any]], rotated_at: datetime
) -> Dict[str, Any]:
    payload = dict(settings or {})
    security = dict(payload.get("security", {}))
    security["default_user_last_rotation"] = rotated_at.isoformat()
    payload["security"] = security
    return payload


def _build_default_user(existing: Optional[User] = None) -> Dict[str, Any]:
    payload = dict(DEFAULT_USER_TEMPLATE)

    base_settings: Dict[str, Any] = {}
    if existing and existing.settings:
        base_settings = dict(existing.settings)
    elif payload.get("settings"):
        base_settings = dict(payload["settings"])

    password = ensure_default_user_password_is_secure()
    if password is None:
        payload["is_active"] = False
        if existing is not None:
            payload["hashed_password"] = existing.hashed_password
            payload["settings"] = dict(existing.settings or base_settings)
        else:
            placeholder = secrets.token_hex(32)
            payload["hashed_password"] = _hash_password(placeholder)
            payload["settings"] = base_settings
        return payload

    hashed = _hash_password(password)
    payload["hashed_password"] = hashed
    payload["is_active"] = True

    if existing and existing.hashed_password == hashed:
        payload["settings"] = dict(existing.settings or base_settings)
    else:
        rotated_at = datetime.now(timezone.utc)
        payload["settings"] = _update_default_user_rotation_settings(
            base_settings, rotated_at
        )
    return payload


def seed_default_user() -> None:
    with session_scope() as db:
        existing = db.query(User).filter(User.id == DEFAULT_USER_TEMPLATE["id"]).first()
        payload = _build_default_user(existing)

        if existing:
            has_changes = False
            for key, value in payload.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    has_changes = True
            if has_changes:
                db.add(existing)
            return

        db.add(User(**payload))


def seed_default_nsfw_settings() -> None:
    with session_scope() as db:
        existing = (
            db.query(NSFWSettings)
            .filter(NSFWSettings.user_id.is_(None))
            .order_by(NSFWSettings.id.asc())
            .first()
        )
        if existing:
            return
        db.add(NSFWSettings(**DEFAULT_NSFW_SETTINGS))


async def init_database() -> None:
    ensure_default_user_password_is_secure()
    data_root = settings.media_directory.parent
    data_root.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(run_migrations)
    await asyncio.to_thread(seed_default_user)
    await asyncio.to_thread(seed_default_nsfw_settings)


def get_default_user_last_rotation() -> Optional[datetime]:
    with session_scope() as db:
        user = db.query(User).filter(User.id == DEFAULT_USER_TEMPLATE["id"]).first()
        if not user or not user.settings:
            return None

        security = user.settings.get("security") if isinstance(user.settings, dict) else None
        if not security:
            return None

        raw_timestamp = security.get("default_user_last_rotation")
        if not raw_timestamp:
            return None

        try:
            timestamp = datetime.fromisoformat(raw_timestamp)
        except ValueError:
            return None

        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseService:
    def __init__(self):
        self._ensure_runtime_bind()
        ensure_schema()
        self.db: Session = SessionLocal()

    @staticmethod
    def _ensure_runtime_bind() -> None:
        global engine, SessionLocal

        desired_url = secret_manager.get("SEIDRA_DATABASE_URL")
        if not desired_url:
            return

        current_url = str(engine.url)
        if current_url == desired_url:
            return

        engine.dispose()
        engine = create_engine(desired_url, echo=False, future=True)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Le changement de moteur signifie que nous pointons vers une nouvelle
        # base SQLite (par exemple, pour un test d'intégration). Forçons la
        # recréation du schéma pour éviter les erreurs « no such table ».
        global _SCHEMA_INITIALISED
        _SCHEMA_INITIALISED = False

        module = sys.modules.get(_ACTIVE_MODULE_ALIAS)
        if module is not None:
            module.engine = engine
            module.SessionLocal = SessionLocal

    @staticmethod
    def _normalize_metadata(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        if "metadata" in kwargs and "metadata_payload" not in kwargs:
            kwargs = dict(kwargs)
            kwargs["metadata_payload"] = kwargs.pop("metadata")
        return kwargs

    def __enter__(self) -> DatabaseService:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if exc:
            self.db.rollback()
        self.close()

    def close(self):
        self.db.close()

    # User operations -----------------------------------------------------
    def create_user(self, username: str, email: str, hashed_password: str) -> User:
        user = User(username=username, email=email, hashed_password=hashed_password)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email).first()

    def update_user_settings(self, user_id: int, **settings_updates: Any) -> Optional[User]:
        user = self.get_user(user_id)
        if not user:
            return None

        current_settings = user.settings if isinstance(user.settings, dict) else {}
        merged_settings = _merge_user_settings(current_settings, settings_updates)
        user.settings = merged_settings
        self.db.commit()
        self.db.refresh(user)
        return user

    # Persona operations --------------------------------------------------
    def create_persona(self, user_id: int, **kwargs: Any) -> Persona:
        payload = self._normalize_metadata(kwargs)
        persona = Persona(user_id=user_id, **payload)
        self.db.add(persona)
        self.db.commit()
        self.db.refresh(persona)
        return persona

    def get_personas(
        self,
        user_id: int,
        *,
        limit: Optional[int] = None,
        offset: int = 0,
        search: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        include_nsfw: bool = False,
        return_total: bool = False,
    ) -> List[Persona] | Tuple[List[Persona], int]:
        query = self.db.query(Persona).filter(Persona.user_id == user_id)

        if not include_nsfw:
            query = query.filter(Persona.is_nsfw.is_(False))

        if is_favorite is not None:
            query = query.filter(Persona.is_favorite.is_(is_favorite))

        if search:
            like_pattern = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(Persona.name).like(like_pattern),
                    func.lower(Persona.description).like(like_pattern),
                    func.lower(Persona.style_prompt).like(like_pattern),
                    func.lower(Persona.tags.cast(String)).like(like_pattern),
                )
            )

        total = query.count() if return_total else 0
        query = query.order_by(Persona.created_at.desc())

        if offset:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        personas = query.all()
        if return_total:
            return personas, total
        return personas

    def get_persona(self, persona_id: int, user_id: int) -> Optional[Persona]:
        return (
            self.db.query(Persona)
            .filter(Persona.id == persona_id, Persona.user_id == user_id)
            .first()
        )

    def update_persona(self, persona_id: int, user_id: int, **kwargs: Any) -> Optional[Persona]:
        persona = self.get_persona(persona_id, user_id)
        if not persona:
            return None

        for key, value in self._normalize_metadata(kwargs).items():
            setattr(persona, key, value)
        persona.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(persona)
        return persona

    def delete_persona(self, persona_id: int, user_id: int) -> bool:
        persona = self.get_persona(persona_id, user_id)
        if not persona:
            return False
        self.db.delete(persona)
        self.db.commit()
        return True

    # Generation metrics -------------------------------------------------
    def create_generation_metric(self, **kwargs: Any) -> GenerationMetric:
        payload = self._normalize_metadata(kwargs)
        metric = GenerationMetric(**payload)
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def list_generation_metrics(
        self,
        *,
        limit: int = 50,
        since_minutes: Optional[int] = None,
        media_type: Optional[str] = None,
    ) -> List[GenerationMetric]:
        query = self.db.query(GenerationMetric)
        if media_type:
            query = query.filter(GenerationMetric.media_type == media_type)
        if since_minutes is not None:
            threshold = datetime.utcnow() - timedelta(minutes=since_minutes)
            query = query.filter(GenerationMetric.created_at >= threshold)
        return (
            query.order_by(GenerationMetric.created_at.desc())
            .limit(limit)
            .all()
        )

    def aggregate_generation_metrics(
        self,
        *,
        since_minutes: Optional[int] = None,
        media_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.db.query(
            func.count(GenerationMetric.id),
            func.avg(GenerationMetric.duration_seconds),
            func.avg(GenerationMetric.throughput),
            func.avg(GenerationMetric.vram_peak_mb),
            func.avg(GenerationMetric.vram_delta_mb),
            func.sum(GenerationMetric.outputs),
        )
        if media_type:
            query = query.filter(GenerationMetric.media_type == media_type)
        if since_minutes is not None:
            threshold = datetime.utcnow() - timedelta(minutes=since_minutes)
            query = query.filter(GenerationMetric.created_at >= threshold)

        count, avg_duration, avg_throughput, avg_peak, avg_delta, total_outputs = query.one()
        return {
            "total": int(count or 0),
            "averageDurationSeconds": float(avg_duration) if avg_duration is not None else None,
            "averageThroughput": float(avg_throughput) if avg_throughput is not None else None,
            "averagePeakVramMb": float(avg_peak) if avg_peak is not None else None,
            "averageDeltaVramMb": float(avg_delta) if avg_delta is not None else None,
            "outputs": int(total_outputs or 0),
        }

    @staticmethod
    def serialize_generation_metric(metric: GenerationMetric) -> Dict[str, Any]:
        return {
            "id": metric.id,
            "jobId": metric.job_id,
            "userId": metric.user_id,
            "personaId": metric.persona_id,
            "mediaType": metric.media_type,
            "modelName": metric.model_name,
            "prompt": metric.prompt,
            "outputs": metric.outputs,
            "durationSeconds": metric.duration_seconds,
            "throughput": metric.throughput,
            "vramAllocatedMb": metric.vram_allocated_mb,
            "vramReservedMb": metric.vram_reserved_mb,
            "vramPeakMb": metric.vram_peak_mb,
            "vramDeltaMb": metric.vram_delta_mb,
            "extra": metric.extra or {},
            "createdAt": metric.created_at.isoformat() if metric.created_at else None,
        }

    # Notifications -------------------------------------------------------
    def create_notification(self, **kwargs: Any) -> Notification:
        payload = self._normalize_metadata(kwargs)
        payload.setdefault("id", str(uuid.uuid4()))
        notification = Notification(**payload)
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification

    def list_notifications(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[Notification], int]:
        query = self.db.query(Notification)
        total = query.count()
        normalized_limit = max(limit, 0)
        normalized_offset = max(offset, 0)
        items = (
            query.order_by(Notification.created_at.desc())
            .offset(normalized_offset)
            .limit(normalized_limit)
            .all()
        )
        return items, total

    @staticmethod
    def serialize_notification(notification: Notification) -> Dict[str, Any]:
        return {
            "id": notification.id,
            "level": notification.level,
            "title": notification.title,
            "message": notification.message,
            "category": notification.category,
            "metadata": notification.metadata_payload or {},
            "tags": notification.tags or [],
            "timestamp": notification.created_at.isoformat()
            if notification.created_at
            else datetime.utcnow().isoformat(),
        }

    def delete_notifications_older_than(
        self,
        cutoff: datetime,
        *,
        levels: Iterable[str] | None = None,
    ) -> int:
        query = self.db.query(Notification).filter(Notification.created_at < cutoff)
        if levels:
            query = query.filter(Notification.level.in_(list(levels)))
        deleted = query.delete(synchronize_session=False)
        self.db.commit()
        return int(deleted)

    # Generation jobs -----------------------------------------------------
    def create_job(self, **kwargs: Any) -> GenerationJob:
        payload = self._normalize_metadata(kwargs)
        job = GenerationJob(**payload)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> Optional[GenerationJob]:
        return self.db.query(GenerationJob).filter(GenerationJob.id == job_id).first()

    def update_job(self, job_id: str, **kwargs: Any) -> Optional[GenerationJob]:
        job = self.get_job(job_id)
        if not job:
            return None
        for key, value in self._normalize_metadata(kwargs).items():
            setattr(job, key, value)
        if "updated_at" in job.__dict__:
            job.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job_payload(self, job: GenerationJob) -> Dict[str, Any]:
        payload = job.parameters or {}
        return payload if isinstance(payload, dict) else {}

    def find_stuck_jobs(self, older_than_minutes: int = 10) -> List[GenerationJob]:
        threshold = datetime.utcnow() - timedelta(minutes=older_than_minutes)
        return (
            self.db.query(GenerationJob)
            .filter(GenerationJob.status == "processing")
            .filter(GenerationJob.updated_at < threshold)
            .all()
        )

    def find_failed_jobs(self, limit: int = 10, newer_than_minutes: Optional[int] = None) -> List[GenerationJob]:
        query = self.db.query(GenerationJob).filter(GenerationJob.status == "failed")
        if newer_than_minutes is not None:
            threshold = datetime.utcnow() - timedelta(minutes=newer_than_minutes)
            query = query.filter(GenerationJob.updated_at >= threshold)
        return query.order_by(GenerationJob.updated_at.desc()).limit(limit).all()

    def reset_job_for_retry(self, job: GenerationJob, *, reason: str) -> GenerationJob:
        metadata = job.metadata_payload or {}
        recovery = dict(metadata.get("recovery", {}))
        history = list(recovery.get("history", []))
        history.append({
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })
        recovery["history"] = history
        recovery["retries"] = recovery.get("retries", 0) + 1
        recovery["last_reason"] = reason
        metadata["recovery"] = recovery

        job.status = "queued"
        job.progress = 0.0
        job.error_message = None
        job.metadata_payload = metadata
        job.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(job)
        return job
      
    def get_user_jobs(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        persona_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[GenerationJob], int]:
        query = self.db.query(GenerationJob).filter(GenerationJob.user_id == user_id)

        if status:
            query = query.filter(GenerationJob.status == status)

        if job_type:
            query = query.filter(GenerationJob.job_type == job_type)

        if persona_id is not None:
            query = query.filter(GenerationJob.persona_id == persona_id)

        if search:
            like_expr = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(GenerationJob.prompt).like(like_expr),
                    func.lower(GenerationJob.negative_prompt).like(like_expr),
                )
            )

        total = query.count()
        jobs = (
            query.order_by(GenerationJob.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return jobs, total

    def get_job_statistics(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "total": 0,
            "by_status": {},
            "average_duration": None,
            "last_completed": None,
        }

        query = self.db.query(GenerationJob)
        if user_id is not None:
            query = query.filter(GenerationJob.user_id == user_id)

        stats["total"] = query.count()

        status_query = self.db.query(GenerationJob.status, func.count(GenerationJob.id))
        if user_id is not None:
            status_query = status_query.filter(GenerationJob.user_id == user_id)
        status_counts = status_query.group_by(GenerationJob.status).all()
        stats["by_status"] = {status: count for status, count in status_counts}

        completed_jobs = (
            query.filter(GenerationJob.completed_at.isnot(None))
            .order_by(GenerationJob.completed_at.desc())
            .all()
        )

        if completed_jobs:
            durations = [
                (job.completed_at - job.created_at).total_seconds()
                for job in completed_jobs
                if job.completed_at and job.created_at
            ]
            if durations:
                stats["average_duration"] = sum(durations) / len(durations)
            stats["last_completed"] = completed_jobs[0].completed_at.isoformat()

        return stats
    # Media ---------------------------------------------------------------
    def create_media_item(self, **kwargs: Any) -> MediaItem:
        payload = self._normalize_metadata(kwargs)
        media = MediaItem(**payload)
        self.db.add(media)
        self.db.commit()
        self.db.refresh(media)
        return media
      
    def get_media_items(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        favorites_only: bool = False,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        persona_id: Optional[int] = None,
    ) -> Tuple[List[MediaItem], int]:
        query = self.db.query(MediaItem).filter(MediaItem.user_id == user_id)

        if favorites_only:
            query = query.filter(MediaItem.is_favorite.is_(True))

        if persona_id is not None:
            query = query.join(GenerationJob, MediaItem.job_id == GenerationJob.id).filter(
                GenerationJob.persona_id == persona_id
            )

        if date_from is not None:
            query = query.filter(MediaItem.created_at >= date_from)

        if date_to is not None:
            query = query.filter(MediaItem.created_at <= date_to)

        if tags:
            normalized_tags = [tag.lower() for tag in tags if tag]
            if normalized_tags:
                tag_table = func.json_each(MediaItem.tags).table_valued("value").alias(
                    "media_tags"
                )
                tag_exists = (
                    select(1)
                    .select_from(tag_table)
                    .where(func.lower(tag_table.c.value).in_(normalized_tags))
                    .correlate(MediaItem)
                    .exists()
                )
                query = query.filter(tag_exists)

        if search:
            search_pattern = f"%{search.lower()}%"
            search_conditions = []

            prompt_expr = func.lower(
                func.coalesce(func.json_extract(MediaItem.metadata_payload, "$.prompt"), "")
            )
            search_conditions.append(prompt_expr.like(search_pattern))

            tag_search_table = func.json_each(MediaItem.tags).table_valued("value").alias(
                "search_tags"
            )
            tag_search_exists = (
                select(1)
                .select_from(tag_search_table)
                .where(func.lower(tag_search_table.c.value).like(search_pattern))
                .correlate(MediaItem)
                .exists()
            )
            search_conditions.append(tag_search_exists)

            query = query.filter(or_(*search_conditions))

        total = query.with_entities(func.count()).scalar() or 0

        ordered_query = query.order_by(MediaItem.created_at.desc())
        if offset:
            ordered_query = ordered_query.offset(offset)
        if limit is not None:
            ordered_query = ordered_query.limit(limit)

        return ordered_query.all(), total

    def get_media_item(self, media_id: str, user_id: int) -> Optional[MediaItem]:
        return (
            self.db.query(MediaItem)
            .filter(MediaItem.id == media_id, MediaItem.user_id == user_id)
            .first()
        )

    def get_media_by_id(self, media_id: str) -> Optional[MediaItem]:
        return self.db.query(MediaItem).filter(MediaItem.id == media_id).first()

    def update_media_item(self, media_id: str, user_id: int, **updates: Any) -> Optional[MediaItem]:
        media = self.get_media_item(media_id, user_id)
        if not media:
            return None

        for key, value in self._normalize_metadata(updates).items():
            setattr(media, key, value)
        if "updated_at" not in updates:
            media.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(media)
        return media

    def get_media_statistics(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        query = self.db.query(MediaItem)
        if user_id is not None:
            query = query.filter(MediaItem.user_id == user_id)
        media_items = query.order_by(MediaItem.created_at.desc()).all()

        total_size_bytes = 0
        for item in media_items:
            if item.file_path and os.path.exists(item.file_path):
                total_size_bytes += os.path.getsize(item.file_path)

        by_persona: Dict[str, int] = {}
        for item in media_items:
            job = (
                self.db.query(GenerationJob)
                .filter(GenerationJob.id == item.job_id)
                .first()
            )
            if job and job.persona_id is not None:
                key = str(job.persona_id)
                by_persona[key] = by_persona.get(key, 0) + 1

        by_date: Dict[str, int] = {}
        for item in media_items:
            key = item.created_at.strftime("%Y-%m-%d")
            by_date[key] = by_date.get(key, 0) + 1

        return {
            "total_images": len(media_items),
            "favorites_count": sum(1 for item in media_items if item.is_favorite),
            "recent_count": sum(
                1
                for item in media_items
                if (datetime.utcnow() - item.created_at).days <= 7
            ),
            "total_size_bytes": total_size_bytes,
            "by_persona": by_persona,
            "by_date": by_date,
        }

    def delete_media_item(self, media_id: str, user_id: int) -> bool:
        media = (
            self.db.query(MediaItem)
            .filter(MediaItem.id == media_id, MediaItem.user_id == user_id)
            .first()
        )
        if not media:
            return False
        self.db.delete(media)
        self.db.commit()
        return True

    def list_pending_jobs(self, before: Optional[datetime] = None) -> List[GenerationJob]:
        query = self.db.query(GenerationJob).filter(GenerationJob.status == "pending")
        if before is not None:
            query = query.filter(GenerationJob.created_at <= before)
        return query.order_by(GenerationJob.created_at.asc()).all()

    def get_platform_summary(self) -> Dict[str, int]:
        """Aggregate high-level entity counts for dashboards."""

        return {
            "users": self.db.query(User).count(),
            "personas": self.db.query(Persona).count(),
            "jobs": self.db.query(GenerationJob).count(),
            "media": self.db.query(MediaItem).count(),
        }

    # LoRA ----------------------------------------------------------------
    def create_lora_model(self, **kwargs: Any) -> LoRAModel:
        lora = LoRAModel(**kwargs)
        self.db.add(lora)
        self.db.commit()
        self.db.refresh(lora)
        return lora

    # NSFW settings -------------------------------------------------------
    def get_nsfw_settings(self, user_id: Optional[int] = None) -> Optional[NSFWSettings]:
        query = self.db.query(NSFWSettings)
        if user_id is not None:
            query = query.filter(NSFWSettings.user_id == user_id)
        else:
            query = query.filter(NSFWSettings.user_id.is_(None))
        return query.order_by(NSFWSettings.updated_at.desc()).first()

    def upsert_nsfw_settings(self, *, user_id: Optional[int], **payload: Any) -> NSFWSettings:
        settings_record = self.get_nsfw_settings(user_id)
        if settings_record is None:
            settings_record = NSFWSettings(user_id=user_id, **payload)
            self.db.add(settings_record)
        else:
            for key, value in payload.items():
                setattr(settings_record, key, value)
        self.db.commit()
        self.db.refresh(settings_record)
        return settings_record

    def get_lora_models(self) -> List[LoRAModel]:
        return self.db.query(LoRAModel).all()

    def update_lora_model(self, model_id: str, **kwargs: Any) -> Optional[LoRAModel]:
        lora = self.db.query(LoRAModel).filter(LoRAModel.id == model_id).first()
        if not lora:
            return None
        for key, value in kwargs.items():
            setattr(lora, key, value)
        self.db.commit()
        self.db.refresh(lora)
        return lora

    # Video timelines ----------------------------------------------------
    def create_video_timeline(
        self,
        *,
        timeline_id: str,
        user_id: int,
        name: str,
        description: str,
        frame_rate: int,
        total_duration: float,
        assets: List[Dict[str, Any]],
        clips: List[Dict[str, Any]],
        job_id: Optional[str] = None,
    ) -> VideoTimeline:
        timeline = VideoTimeline(
            id=timeline_id,
            user_id=user_id,
            name=name,
            description=description,
            frame_rate=frame_rate,
            total_duration=total_duration,
            timeline_payload={"assets": assets, "clips": clips},
            job_id=job_id,
        )
        self.db.add(timeline)
        self.db.commit()
        self.db.refresh(timeline)
        return timeline

    def update_video_timeline(
        self,
        timeline_id: str,
        user_id: int,
        **updates: Any,
    ) -> Optional[VideoTimeline]:
        timeline = (
            self.db.query(VideoTimeline)
            .filter(VideoTimeline.id == timeline_id, VideoTimeline.user_id == user_id)
            .first()
        )
        if timeline is None:
            return None

        payload = dict(self._normalize_metadata(updates))
        timeline_updates = payload.pop("timeline", None)
        for key, value in payload.items():
            setattr(timeline, key, value)
        if timeline_updates is not None:
            timeline.timeline_payload = timeline_updates
        self.db.commit()
        self.db.refresh(timeline)
        return timeline

    def get_video_timeline(self, timeline_id: str, user_id: int) -> Optional[VideoTimeline]:
        return (
            self.db.query(VideoTimeline)
            .filter(VideoTimeline.id == timeline_id, VideoTimeline.user_id == user_id)
            .first()
        )

    def list_video_timelines(self, user_id: int) -> List[VideoTimeline]:
        return (
            self.db.query(VideoTimeline)
            .filter(VideoTimeline.user_id == user_id)
            .order_by(VideoTimeline.updated_at.desc())
            .all()
        )

    # Utility -------------------------------------------------------------
    def clear(self):
        self.db.query(MediaItem).delete()
        self.db.query(GenerationJob).delete()
        self.db.query(Persona).delete()
        self.db.query(NSFWSettings).delete()
        self.db.query(User).delete()
        self.db.commit()


def _deep_merge_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep-merged copy of ``base`` updated with ``updates``."""

    merged: Dict[str, Any] = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _merge_user_settings(existing: Optional[Dict[str, Any]], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Combine defaults, existing settings and updates using deep merge semantics."""

    base_settings = deepcopy(DEFAULT_SETTINGS)

    if isinstance(existing, dict) and existing:
        base_settings = _deep_merge_dict(base_settings, existing)

    if updates:
        base_settings = _deep_merge_dict(base_settings, updates)

    return base_settings
