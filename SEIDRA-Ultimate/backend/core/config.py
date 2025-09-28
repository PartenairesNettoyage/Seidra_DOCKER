"""Configuration helpers for the SEIDRA Ultimate backend.

This module centralises runtime configuration so the application can share
consistent defaults between the FastAPI app, Celery workers and background
utilities. Values can be overridden through environment variables without
changing the codebase, ensuring parity with the production-ready SEIDRA
stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:  # pragma: no cover - compatibilité pydantic v1/v2
    from pydantic import BaseModel, Field, field_validator, model_validator
except ImportError:  # pragma: no cover - environnement pydantic v1
    from pydantic import BaseModel, Field, root_validator, validator  # type: ignore

    def field_validator(*fields: str, mode: str = "after", **kwargs: Any):  # type: ignore
        """Shim pour `field_validator` en environnement Pydantic v1."""

        pre = mode == "before"

        def decorator(func: Any) -> Any:
            return validator(*fields, pre=pre, allow_reuse=kwargs.get("allow_reuse", False))(func)

        return decorator

    def model_validator(*fields: str, mode: str = "after", **kwargs: Any):  # type: ignore
        """Shim pour `model_validator` en environnement Pydantic v1."""

        pre = mode == "before"
        return root_validator(pre=pre, allow_reuse=kwargs.get("allow_reuse", False))
try:  # pragma: no cover - compatibilité pydantic v1/v2
    from pydantic_core import PydanticUndefined
except ImportError:  # pragma: no cover - environnement pydantic v1
    try:
        from pydantic.fields import Undefined as PydanticUndefined  # type: ignore
    except ImportError:  # pragma: no cover - fallback minimal
        PydanticUndefined = object()

try:  # pragma: no cover - dépend des extras installés
    from pydantic_settings import BaseSettings as _BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - repli en environnement minimal
    try:
        from pydantic import (
            BaseSettings as _BaseSettings,  # type: ignore[attr-defined]
            ConfigDict as SettingsConfigDict,  # type: ignore[attr-defined]
        )
    except ImportError:  # pragma: no cover - contexte de tests sans pydantic complet
        class _BaseSettings(BaseModel):  # type: ignore[misc, valid-type]
            """Fallback minimaliste utilisé par les tests offline."""

            model_config = {"extra": "allow"}

        def SettingsConfigDict(**config: Any) -> dict[str, Any]:  # type: ignore[override]
            return config

try:
    import boto3
except ImportError:  # pragma: no cover - boto3 est optionnel
    boto3 = None


LOGGER = logging.getLogger("seidra.config")


class SecretRetrievalError(RuntimeError):
    """Erreurs déclenchées lors du chargement des secrets."""


class SecretNotFoundError(KeyError):
    """Secret introuvable dans la source configurée."""


@dataclass
class SecretRecord:
    """Représente un secret tel que retourné par un backend."""

    value: Any
    metadata: dict[str, Any]


class BaseSecretBackend:
    """Interface minimale pour une source de secrets."""

    def get_secret(
        self, name: str, *, field: str | None = None
    ) -> SecretRecord | None:  # pragma: no cover - interface
        raise NotImplementedError


class VaultSecretBackend(BaseSecretBackend):
    """Backend HashiCorp Vault via l'API HTTP v1."""

    def __init__(
        self,
        *,
        url: str,
        token: str,
        mount_point: str,
        prefix: str,
        namespace: str | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._mount_point = mount_point.strip("/")
        self._prefix = prefix.strip("/")
        self._namespace = namespace

    def _build_path(self, name: str) -> str:
        parts = [self._mount_point]
        if self._prefix:
            parts.append(self._prefix)
        parts.append(name)
        return "/".join(part.strip("/") for part in parts if part)

    def get_secret(
        self, name: str, *, field: str | None = None
    ) -> SecretRecord | None:
        path = self._build_path(name)
        endpoint = f"{self._url}/v1/{path}"
        headers = {"X-Vault-Token": self._token}
        if self._namespace:
            headers["X-Vault-Namespace"] = self._namespace

        request = Request(endpoint, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:  # noqa: S310 - Vault interne
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:  # pragma: no cover - dépend du backend
            if exc.code == 404:
                return None
            raise SecretRetrievalError(
                f"Erreur HTTP {exc.code} en contactant Vault pour {path}"
            ) from exc
        except URLError as exc:  # pragma: no cover - dépend du backend
            raise SecretRetrievalError(
                f"Impossible de contacter Vault ({exc.reason})"
            ) from exc

        data = payload.get("data", {})
        inner = data.get("data", {}) if isinstance(data, dict) else {}

        if not isinstance(inner, dict):
            LOGGER.debug("Secret Vault %s sans structure JSON attendue", path)
            return None

        if field:
            if field in inner:
                return SecretRecord(value=inner[field], metadata={"field": field})
            return None

        if "value" in inner and len(inner) == 1:
            return SecretRecord(value=inner["value"], metadata={})

        return SecretRecord(value=inner, metadata={})


class SSMSecretBackend(BaseSecretBackend):
    """Backend AWS SSM Parameter Store."""

    def __init__(self, *, region_name: str, prefix: str) -> None:
        if boto3 is None:  # pragma: no cover - dépendance optionnelle
            raise SecretRetrievalError(
                "boto3 est requis pour SEIDRA_SECRET_PROVIDER=ssm"
            )

        self._prefix = prefix.rstrip("/")
        self._client = boto3.client("ssm", region_name=region_name)

    def _build_name(self, name: str) -> str:
        if self._prefix:
            return f"{self._prefix}/{name}"
        return name

    def get_secret(
        self, name: str, *, field: str | None = None
    ) -> SecretRecord | None:  # pragma: no cover - dépend du backend
        parameter_name = self._build_name(name)
        try:
            response = self._client.get_parameter(
                Name=parameter_name, WithDecryption=True
            )
        except self._client.exceptions.ParameterNotFound:
            return None

        value: str = response["Parameter"]["Value"]
        metadata = {
            "version": response["Parameter"].get("Version"),
            "arn": response["Parameter"].get("ARN"),
        }

        if field:
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return None
            if field in decoded:
                return SecretRecord(value=decoded[field], metadata=metadata)
            return None

        return SecretRecord(value=value, metadata=metadata)


class SecretManager:
    """Centralise l'accès aux secrets applicatifs."""

    def __init__(self) -> None:
        self._provider = os.getenv("SEIDRA_SECRET_PROVIDER", "env").lower()
        self._cache: dict[str, SecretRecord] = {}
        self._lock = threading.Lock()
        self._backend: BaseSecretBackend | None = None

    def _ensure_backend(self) -> BaseSecretBackend | None:
        if self._provider in {"", "env"}:
            return None

        if self._backend is not None:
            return self._backend

        with self._lock:
            if self._backend is not None:
                return self._backend

            if self._provider == "vault":
                url = os.getenv("SEIDRA_VAULT_ADDR") or os.getenv("VAULT_ADDR")
                token = os.getenv("SEIDRA_VAULT_TOKEN") or os.getenv("VAULT_TOKEN")
                mount_point = os.getenv("SEIDRA_VAULT_MOUNT_POINT", "secret/data")
                prefix = os.getenv("SEIDRA_VAULT_PREFIX", "seidra")
                namespace = os.getenv("SEIDRA_VAULT_NAMESPACE")

                if not url or not token:
                    raise SecretRetrievalError(
                        "Vault nécessite SEIDRA_VAULT_ADDR/VAULT_ADDR et "
                        "SEIDRA_VAULT_TOKEN/VAULT_TOKEN."
                    )

                self._backend = VaultSecretBackend(
                    url=url,
                    token=token,
                    mount_point=mount_point,
                    prefix=prefix,
                    namespace=namespace,
                )
            elif self._provider == "ssm":
                region = os.getenv("SEIDRA_SSM_REGION") or os.getenv("AWS_REGION")
                prefix = os.getenv("SEIDRA_SSM_PREFIX", "/seidra")
                if not region:
                    raise SecretRetrievalError(
                        "SSM nécessite SEIDRA_SSM_REGION ou AWS_REGION."
                    )
                self._backend = SSMSecretBackend(region_name=region, prefix=prefix)
            else:
                raise SecretRetrievalError(
                    f"SEIDRA_SECRET_PROVIDER={self._provider} est inconnu"
                )

        return self._backend

    def clear_cache(self) -> None:
        self._cache.clear()

    def get(
        self,
        name: str,
        *,
        default: Any | None = None,
        required: bool = False,
        field: str | None = None,
    ) -> Any | None:
        if name in self._cache:
            return self._cache[name].value

        env_override = os.getenv(name)
        if env_override is not None:
            if field:
                try:
                    parsed = json.loads(env_override)
                except json.JSONDecodeError:
                    LOGGER.debug(
                        "Le secret %s ne peut pas être parsé en JSON pour le champ %s",
                        name,
                        field,
                    )
                else:
                    if field in parsed:
                        self._cache[name] = SecretRecord(
                            value=parsed[field], metadata={"field": field}
                        )
                        return parsed[field]
                    LOGGER.debug(
                        "Champ %s absent de la valeur JSON de %s", field, name
                    )
            self._cache[name] = SecretRecord(value=env_override, metadata={})
            return env_override

        backend = self._ensure_backend()
        if backend is None:
            if required and default is None:
                raise SecretNotFoundError(name)
            return default

        record = backend.get_secret(name, field=field)
        if record is None:
            if required and default is None:
                raise SecretNotFoundError(name)
            return default

        self._cache[name] = record
        return record.value


secret_manager = SecretManager()


class NotificationThresholds(BaseModel):
    """Seuils configurables pour les alertes systèmes."""

    gpu_temperature_warning: float = Field(80.0, description="Seuil d'alerte (°C) pour la température GPU")
    gpu_temperature_critical: float = Field(85.0, description="Seuil critique (°C) pour la température GPU")
    gpu_memory_warning: float = Field(
        0.85,
        ge=0.0,
        le=1.0,
        description="Seuil d'alerte pour l'utilisation mémoire GPU (ratio 0-1)",
    )
    gpu_memory_critical: float = Field(
        0.95,
        ge=0.0,
        le=1.0,
        description="Seuil critique pour l'utilisation mémoire GPU (ratio 0-1)",
    )
    cpu_usage_warning: float = Field(90.0, description="Seuil d'alerte pour l'utilisation CPU (%)")
    ram_usage_warning: float = Field(90.0, description="Seuil d'alerte pour l'utilisation RAM (%)")
    queue_warning: int = Field(10, ge=0, description="Seuil d'alerte pour la file d'attente de génération")
    queue_critical: int = Field(25, ge=0, description="Seuil critique pour la file d'attente de génération")


def _parse_level_list(value: Any, *, default: list[str]) -> list[str]:
    """Normalise les niveaux d'alerte fournis via l'environnement."""

    if value in (None, ""):
        return default
    if isinstance(value, str):
        items = [item.strip().lower() for item in value.split(",") if item.strip()]
        return items or default
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip().lower() for item in value if str(item).strip()]
        return items or default
    return default


class SlackNotificationSettings(BaseModel):
    """Configuration du connecteur webhook Slack."""

    enabled: bool = Field(
        False,
        description="Active l'envoi des alertes vers un webhook Slack.",
    )
    webhook_url: str | None = Field(
        None,
        description="URL du webhook entrant Slack.",
    )
    username: str = Field(
        "SEIDRA Ultimate",
        description="Nom d'affichage utilisé pour les messages Slack.",
    )
    icon_emoji: str | None = Field(
        ":robot_face:",
        description="Emoji facultatif affiché avec le message Slack.",
    )
    levels: list[str] = Field(
        default_factory=lambda: ["error", "critical"],
        description="Niveaux de notification propagés au webhook Slack.",
    )

    @field_validator("levels", mode="before")
    @classmethod
    def _normalise_levels(cls, value: Any) -> list[str]:
        return _parse_level_list(value, default=["error", "critical"])


class PagerDutyNotificationSettings(BaseModel):
    """Configuration du connecteur PagerDuty Events API v2."""

    enabled: bool = Field(
        False,
        description="Active la création d'événements PagerDuty.",
    )
    routing_key: str | None = Field(
        None,
        description="Clé d'intégration Events API (routing key).",
    )
    api_url: str = Field(
        "https://events.pagerduty.com/v2/enqueue",
        description="Endpoint Events API utilisé pour publier les alertes.",
    )
    source: str = Field(
        "seidra-backend",
        description="Valeur du champ `source` dans le payload PagerDuty.",
    )
    client: str = Field(
        "SEIDRA Ultimate",
        description="Nom du client affiché dans PagerDuty.",
    )
    dedup_key_prefix: str | None = Field(
        "seidra-",
        description="Préfixe facultatif appliqué au dedup_key PagerDuty.",
    )
    levels: list[str] = Field(
        default_factory=lambda: ["error", "critical"],
        description="Niveaux de notification propagés à PagerDuty.",
    )

    @field_validator("levels", mode="before")
    @classmethod
    def _normalise_levels(cls, value: Any) -> list[str]:
        return _parse_level_list(value, default=["error", "critical"])


class RemoteServiceSettings(BaseModel):
    """Paramétrage fin des appels vers un service d'inférence distant."""

    request_timeout_seconds: float = Field(
        90.0,
        ge=1.0,
        description="Timeout total appliqué aux requêtes HTTP (en secondes).",
    )
    connect_timeout_seconds: float = Field(
        10.0,
        ge=0.1,
        description="Timeout de connexion TCP (en secondes).",
    )
    read_timeout_seconds: float = Field(
        80.0,
        ge=0.1,
        description="Timeout de lecture des réponses HTTP (en secondes).",
    )
    write_timeout_seconds: float = Field(
        80.0,
        ge=0.1,
        description="Timeout d'écriture/streaming des requêtes HTTP (en secondes).",
    )
    max_attempts: int = Field(
        3,
        ge=1,
        description="Nombre maximal de tentatives avant de déclarer l'appel en échec.",
    )
    backoff_factor: float = Field(
        1.5,
        ge=0.0,
        description="Facteur multiplicatif appliqué entre chaque retry (backoff exponentiel).",
    )
    backoff_max_seconds: float = Field(
        30.0,
        ge=0.1,
        description="Délai maximal entre deux tentatives (en secondes).",
    )
    queue_retry_delay_seconds: float = Field(
        20.0,
        ge=0.0,
        description="Délai d'attente avant une nouvelle tentative en file locale (en secondes).",
    )
    queue_max_retries: int = Field(
        5,
        ge=0,
        description="Nombre maximum de tentatives additionnelles effectuées par la file locale.",
    )


class RemoteInferenceSettings(BaseModel):
    """Regroupe les paramètres de résilience pour ComfyUI et SadTalker."""

    comfyui: RemoteServiceSettings = Field(
        default_factory=lambda: RemoteServiceSettings(
            request_timeout_seconds=90.0,
            read_timeout_seconds=90.0,
            write_timeout_seconds=90.0,
            queue_retry_delay_seconds=15.0,
        ),
        description="Paramètres dédiés aux appels ComfyUI.",
    )
    sadtalker: RemoteServiceSettings = Field(
        default_factory=lambda: RemoteServiceSettings(
            request_timeout_seconds=120.0,
            read_timeout_seconds=110.0,
            write_timeout_seconds=110.0,
            queue_retry_delay_seconds=25.0,
        ),
        description="Paramètres dédiés aux appels SadTalker.",
    )

    def for_service(self, service: str) -> RemoteServiceSettings:
        lookup = service.lower()
        if lookup == "comfyui":
            return self.comfyui
        if lookup == "sadtalker":
            return self.sadtalker
        raise KeyError(f"Service distant inconnu: {service}")

class RateLimitPolicy(BaseModel):
    """Politique de limitation de débit mixant quotas globaux et utilisateurs."""

    global_quota: int = Field(
        0,
        ge=0,
        description="Nombre maximal de requêtes autorisées globalement sur la fenêtre",
    )
    global_window_seconds: int = Field(
        60,
        ge=1,
        description="Durée de la fenêtre globale en secondes",
    )
    user_quota: int = Field(
        0,
        ge=0,
        description="Nombre maximal de requêtes autorisées par utilisateur",
    )
    user_window_seconds: int = Field(
        60,
        ge=1,
        description="Durée de la fenêtre utilisateur en secondes",
    )

    @staticmethod
    def _compose(quota: int, window_seconds: int) -> str:
        if quota <= 0:
            return "illimité"
        if window_seconds % 3600 == 0:
            hours = window_seconds // 3600
            unit = "heure" if hours == 1 else "heures"
            return f"{quota}/{hours} {unit}"
        if window_seconds % 60 == 0:
            minutes = window_seconds // 60
            unit = "minute" if minutes == 1 else "minutes"
            return f"{quota}/{minutes} {unit}"
        unit = "seconde" if window_seconds == 1 else "secondes"
        return f"{quota}/{window_seconds} {unit}"

    def describe(self) -> str:
        """Retourne une description textuelle lisible des quotas."""

        parts: list[str] = []
        if self.global_quota:
            parts.append(f"global: {self._compose(self.global_quota, self.global_window_seconds)}")
        if self.user_quota:
            parts.append(
                f"utilisateur: {self._compose(self.user_quota, self.user_window_seconds)}"
            )
        if not parts:
            return "illimité"
        return " ; ".join(parts)


class Settings(_BaseSettings):
    """Application settings loaded from environment variables."""

    environment: str = Field("development", env="SEIDRA_ENV")
    debug: bool = Field(False, env="SEIDRA_DEBUG")

    database_url: str = Field("sqlite:///../data/seidra.db", env="SEIDRA_DATABASE_URL")
    media_dir: Path = Field(Path("../data/media"), env="SEIDRA_MEDIA_DIR")
    thumbnail_dir: Path = Field(Path("../data/media/thumbnails"), env="SEIDRA_THUMBNAIL_DIR")
    models_dir: Path = Field(Path("../data/models"), env="SEIDRA_MODELS_DIR")
    temp_dir: Path = Field(Path("../data/tmp"), env="SEIDRA_TMP_DIR")
    default_user_rotation_days: int = Field(
        90,
        ge=0,
        env="SEIDRA_DEFAULT_USER_ROTATION_DAYS",
        description=(
            "Nombre de jours entre deux rotations recommandées pour le compte démo. "
            "Mettre 0 pour désactiver l'alerte."
        ),
    )

    redis_url: str = Field("redis://localhost:6379/0", env="SEIDRA_REDIS_URL")
    celery_broker_url: str = Field("redis://localhost:6379/1", env="SEIDRA_CELERY_BROKER")
    celery_result_backend: str = Field("redis://localhost:6379/2", env="SEIDRA_CELERY_BACKEND")

    rate_limit_redis_url: str = Field(
        "redis://localhost:6379/3", env="SEIDRA_RATE_LIMIT_REDIS_URL"
    )
    rate_limit_redis_prefix: str = Field(
        "seidra-rate-limit", env="SEIDRA_RATE_LIMIT_REDIS_PREFIX"
    )
    rate_limit_default_policy: RateLimitPolicy = Field(
        default_factory=lambda: RateLimitPolicy(
            global_quota=240,
            global_window_seconds=60,
            user_quota=120,
            user_window_seconds=60,
        ),
        env="SEIDRA_RATE_LIMIT_DEFAULT",
    )
    rate_limit_generation_policy: RateLimitPolicy = Field(
        default_factory=lambda: RateLimitPolicy(
            global_quota=60,
            global_window_seconds=60,
            user_quota=12,
            user_window_seconds=60,
        ),
        env="SEIDRA_RATE_LIMIT_GENERATION",
    )
    rate_limit_media_policy: RateLimitPolicy = Field(
        default_factory=lambda: RateLimitPolicy(
            global_quota=180,
            global_window_seconds=300,
            user_quota=90,
            user_window_seconds=300,
        ),
        env="SEIDRA_RATE_LIMIT_MEDIA",
    )
    rate_limit_auth_policy: RateLimitPolicy = Field(
        default_factory=lambda: RateLimitPolicy(
            global_quota=50,
            global_window_seconds=300,
            user_quota=10,
            user_window_seconds=300,
        ),
        env="SEIDRA_RATE_LIMIT_AUTH",
    )

    websocket_token: str = Field("ultimate-demo-token", env="SEIDRA_WS_TOKEN")
    allow_system_fallback: bool = Field(False, env="SEIDRA_ALLOW_SYSTEM_FALLBACK")

    minio_endpoint: str = Field("http://localhost:9000", env="SEIDRA_MINIO_ENDPOINT")
    minio_access_key: str = Field("admin", env="SEIDRA_MINIO_ACCESS_KEY")
    minio_secret_key: str = Field("password", env="SEIDRA_MINIO_SECRET_KEY")
    minio_bucket: str = Field("seidra-media", env="SEIDRA_MINIO_BUCKET")

    comfyui_url: str = Field("http://localhost:8188", env="SEIDRA_COMFYUI_URL")
    sadtalker_url: str = Field("http://localhost:8002", env="SEIDRA_SADTALKER_URL")

    remote_inference: RemoteInferenceSettings = Field(
        default_factory=RemoteInferenceSettings,
        env="SEIDRA_REMOTE_INFERENCE",
        description="Paramètres de résilience pour les services ComfyUI/SadTalker.",
    )

    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        env="SEIDRA_ALLOWED_ORIGINS",
    )

    notification_thresholds: NotificationThresholds = Field(
        default_factory=NotificationThresholds,
        env="SEIDRA_NOTIFICATION_THRESHOLDS",
    )
    notification_retention_days: int = Field(
        30,
        ge=0,
        env="SEIDRA_NOTIFICATION_RETENTION_DAYS",
        description="Durée de conservation des notifications critiques (jours).",
    )
    notifications_slack: SlackNotificationSettings = Field(
        default_factory=SlackNotificationSettings,
        env="SEIDRA_NOTIFICATIONS_SLACK",
        description="Paramétrage du connecteur webhook Slack.",
    )
    notifications_pagerduty: PagerDutyNotificationSettings = Field(
        default_factory=PagerDutyNotificationSettings,
        env="SEIDRA_NOTIFICATIONS_PAGERDUTY",
        description="Paramétrage du connecteur PagerDuty Events API.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    _SECRET_ENV_FIELDS: ClassVar[dict[str, str]] = {
        "database_url": "SEIDRA_DATABASE_URL",
        "redis_url": "SEIDRA_REDIS_URL",
        "celery_broker_url": "SEIDRA_CELERY_BROKER",
        "celery_result_backend": "SEIDRA_CELERY_BACKEND",
        "rate_limit_redis_url": "SEIDRA_RATE_LIMIT_REDIS_URL",
        "websocket_token": "SEIDRA_WS_TOKEN",
        "minio_access_key": "SEIDRA_MINIO_ACCESS_KEY",
        "minio_secret_key": "SEIDRA_MINIO_SECRET_KEY",
    }

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("media_dir", "thumbnail_dir", "models_dir", "temp_dir", mode="before")
    @classmethod
    def _as_path(cls, value: Any) -> Path:
        return value if isinstance(value, Path) else Path(value)

    @model_validator(mode="after")
    def _load_secret(cls, settings: Settings) -> Settings:
        if isinstance(settings, dict):
            storage: dict[str, Any] = settings

            def getter(name: str) -> Any:
                return storage.get(name)

            def setter(name: str, value: Any) -> None:
                storage[name] = value

            target: Any = settings
        else:
            def getter(name: str) -> Any:
                return getattr(settings, name)

            def setter(name: str, value: Any) -> None:
                setattr(settings, name, value)

            target = settings

        model_fields = getattr(cls, "model_fields", None)
        if model_fields is None:
            model_fields = getattr(cls, "__fields__", {})  # type: ignore[attr-defined]
        for field_name, env_name in cls._SECRET_ENV_FIELDS.items():
            field = model_fields.get(field_name)
            default_value = getter(field_name)
            if default_value is None:
                field_default = None
                if field is not None:
                    field_default = getattr(field, "default", None)
                    if field_default is PydanticUndefined:
                        field_default = None
                    if field_default is None:
                        factory = getattr(field, "default_factory", None)
                        if callable(factory):
                            try:
                                field_default = factory()
                            except TypeError:
                                field_default = None
                if field_default is not None:
                    default_value = field_default
            resolved = secret_manager.get(env_name, default=default_value)
            if resolved is not None:
                setter(field_name, resolved)
            elif default_value is not None:
                setter(field_name, default_value)
        return target

    @property
    def media_directory(self) -> Path:
        return self.media_dir.expanduser().resolve()

    @property
    def thumbnail_directory(self) -> Path:
        return self.thumbnail_dir.expanduser().resolve()

    @property
    def models_directory(self) -> Path:
        return self.models_dir.expanduser().resolve()

    @property
    def tmp_directory(self) -> Path:
        return self.temp_dir.expanduser().resolve()

    @property
    def rate_limit_default(self) -> str:
        return self.rate_limit_default_policy.describe()

    @property
    def rate_limit_generation(self) -> str:
        return self.rate_limit_generation_policy.describe()

    @property
    def rate_limit_media(self) -> str:
        return self.rate_limit_media_policy.describe()

    @property
    def rate_limit_auth(self) -> str:
        return self.rate_limit_auth_policy.describe()


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_runtime_directories(settings: Settings) -> None:
    """Create directories required by the backend."""

    _ensure_directory(settings.media_directory)
    _ensure_directory(settings.thumbnail_directory)
    _ensure_directory(settings.models_directory)
    _ensure_directory(settings.tmp_directory)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
