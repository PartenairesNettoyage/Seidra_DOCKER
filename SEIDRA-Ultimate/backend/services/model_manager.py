"""
SEIDRA Model Manager
Handles Stable Diffusion XL and LoRA model loading/management
RTX 3090 Optimized with graceful CPU/mock fallbacks for local development
"""

from __future__ import annotations

import base64
import copy
import logging
import mimetypes
import os
import time
import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Awaitable, TypeVar, TYPE_CHECKING
from urllib.parse import urljoin

from datetime import UTC, datetime

import httpx
from PIL import Image

from core.config import RemoteServiceSettings, settings
from services.model_repository import DownloadError, ModelRepository

if TYPE_CHECKING:  # pragma: no cover - annotations uniquement
    from services.notifications import NotificationService
    from services.telemetry_service import TelemetryService


LOGGER = logging.getLogger("seidra.model_manager")

try:
    import torch  # type: ignore
    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - torch is optional in the CI container
    TORCH_AVAILABLE = False
    torch = None  # type: ignore

try:  # pragma: no cover - diffusers is optional during tests
    from diffusers import DiffusionPipeline, StableDiffusionXLPipeline  # type: ignore
    from diffusers.loaders import LoraLoaderMixin  # type: ignore
    DIFFUSERS_AVAILABLE = True
except Exception:  # pragma: no cover - diffusers not installed in CI
    DiffusionPipeline = StableDiffusionXLPipeline = LoraLoaderMixin = None  # type: ignore
    DIFFUSERS_AVAILABLE = False

try:  # pragma: no cover - optional GPU monitoring helpers
    import GPUtil  # type: ignore
    GPUTIL_AVAILABLE = True
except Exception:
    GPUTIL_AVAILABLE = False


class MockPipeline:
    """Lightweight placeholder pipeline used when CUDA/diffusers are unavailable."""

    def __init__(self):
        self.loaded_loras: List[str] = []

    def to(self, *_args, **_kwargs):  # pragma: no cover - simple chaining helper
        return self

    def enable_xformers_memory_efficient_attention(self):  # pragma: no cover - mock no-op
        return self

    def enable_model_cpu_offload(self):  # pragma: no cover - mock no-op
        return self

    def enable_sequential_cpu_offload(self):  # pragma: no cover - mock no-op
        return self

    def unload_lora_weights(self):  # pragma: no cover - mock no-op
        self.loaded_loras.clear()

    def load_lora_weights(self, lora_path: str):  # pragma: no cover - store metadata only
        self.loaded_loras.append(lora_path)

    def __call__(self, *_, **__):  # pragma: no cover - deterministic output for tests
        class Result:
            def __init__(self):
                self.images: List[Image.Image] = []

        return Result()


class RTX3090Optimizer:
    """RTX 3090 specific optimizations (used when real pipelines are enabled)."""

    def __init__(self):
        self.vram_limit = 24 * 1024 * 1024 * 1024  # 24GB

    def optimize_pipeline(self, pipeline):  # pragma: no cover - heavy path not hit in CI
        try:
            pipeline.enable_xformers_memory_efficient_attention()
        except Exception:
            print("⚠️ xFormers not available, using default attention")

        if TORCH_AVAILABLE:
            pipeline = pipeline.to(torch.float16)

        try:
            pipeline.enable_model_cpu_offload()
        except Exception:
            print("⚠️ CPU offloading not available")

        try:
            pipeline.enable_sequential_cpu_offload()
        except Exception:
            print("⚠️ Sequential CPU offload not available")

        return pipeline

    def get_optimal_batch_size(self) -> int:
        if not GPUTIL_AVAILABLE:
            return 1

        try:  # pragma: no cover - requires actual GPU
            gpus = GPUtil.getGPUs()
            if gpus:
                available_vram = gpus[0].memoryFree * 1024 * 1024
                if available_vram > 20 * 1024**3:
                    return 4
                if available_vram > 15 * 1024**3:
                    return 3
                if available_vram > 10 * 1024**3:
                    return 2
                return 1
        except Exception:
            pass
        return 1


class ModelCache:
    """Intelligent model caching system"""

    def __init__(self, cache_dir: str, max_size_gb: int = 50):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size_gb * 1024**3
        self.loaded_models: Dict[str, Any] = {}
        self.access_times: Dict[str, float] = {}

    def get_cache_size(self) -> int:
        total_size = 0
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size

    def cleanup_cache(self):  # pragma: no cover - requires large cache
        current_size = self.get_cache_size()
        if current_size <= self.max_size:
            return

        sorted_models = sorted(self.access_times.items(), key=lambda x: x[1])
        for model_id, _ in sorted_models:
            if current_size <= self.max_size * 0.8:
                break
            model_path = self.cache_dir / model_id
            if model_path.exists():
                import shutil

                shutil.rmtree(model_path)
                current_size = self.get_cache_size()
                self.loaded_models.pop(model_id, None)
                self.access_times.pop(model_id, None)


@dataclass
class RemoteRetryJob:
    """Représente une tâche à relancer suite à un échec distant."""

    id: str
    service: str
    action: str
    payload: Dict[str, Any]
    media_dir: Path
    max_attempts: int
    retry_delay: float
    attempts: int = 0
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"{self.action} (service={self.service})"


ProgressCallback = Optional[Callable[[float, str], Awaitable[None]]]
T = TypeVar("T")


class ModelManager:
    """Main model management class with graceful CPU fallbacks."""

    def __init__(self):
        self.models_dir = settings.models_directory
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self.cache = ModelCache(str(self.models_dir / "cache"))
        self.optimizer = RTX3090Optimizer()

        self.base_pipeline: Optional[Any] = None
        self.loaded_models: Dict[str, Any] = {}
        self.lora_models: Dict[str, Dict[str, Any]] = {}
        self._initialized = False

        self.remote_inference = self._should_use_remote_inference()
        self.use_mock_pipeline = self._should_use_mock_pipeline()

        if self.remote_inference:
            mode = "remote"
        elif self.use_mock_pipeline:
            mode = "mock"
        else:
            mode = "cuda"
        self.status: Dict[str, Any] = {
            "initialized": False,
            "mode": mode,
            "current_model": "sdxl-base",
            "loras_loaded": [],
            "last_update": datetime.now(UTC).isoformat(),
            "health": "healthy",
            "last_error": None,
        }
        self._last_known_mode = mode


        self.repository = ModelRepository(self.models_dir, http_client_factory=self._create_http_client)
        self._last_generation_metrics: Optional[Dict[str, Any]] = None
        self._remote_settings = settings.remote_inference
        self._remote_retry_queue: asyncio.Queue[RemoteRetryJob | object] = asyncio.Queue()
        self._queue_worker: Optional[asyncio.Task] = None
        self._queue_shutdown = False
        self._queue_stop_sentinel: object = object()
        self.telemetry_service: Optional["TelemetryService"] = None
        self.notification_service: Optional["NotificationService"] = None


        self.base_models = {
            "sdxl-base": "stabilityai/stable-diffusion-xl-base-1.0",
            "sdxl-refiner": "stabilityai/stable-diffusion-xl-refiner-1.0",
        }

        self.popular_loras = {
            "anime_style": {
                "url": "https://civitai.com/api/download/models/47274",
                "filename": "anime_style.safetensors",
                "category": "style",
            },
            "photorealistic": {
                "url": "https://civitai.com/api/download/models/130072",
                "filename": "photorealistic.safetensors",
                "category": "style",
            },
            "fantasy_art": {
                "url": "https://civitai.com/api/download/models/84040",
                "filename": "fantasy_art.safetensors",
                "category": "style",
            },
        }

    def attach_telemetry_service(self, service: "TelemetryService") -> None:
        self.telemetry_service = service

    def attach_notification_service(self, service: "NotificationService") -> None:
        self.notification_service = service

    def _create_http_client(self, *, service: Optional[str] = None) -> httpx.AsyncClient:
        config = None
        if service:
            try:
                config = self._get_remote_config(service)
            except KeyError:
                config = None

        if config is None:
            timeout = httpx.Timeout(60.0, connect=10.0, read=60.0)
        else:
            timeout = httpx.Timeout(
                config.request_timeout_seconds,
                connect=config.connect_timeout_seconds,
                read=config.read_timeout_seconds,
                write=config.write_timeout_seconds,
            )

        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        return httpx.AsyncClient(timeout=timeout, limits=limits)

    def _should_use_remote_inference(self) -> bool:
        if os.getenv("SEIDRA_USE_REAL_MODELS", "0") == "1":
            return False
        if not TORCH_AVAILABLE or not DIFFUSERS_AVAILABLE:
            return True
        if TORCH_AVAILABLE and not torch.cuda.is_available():  # type: ignore[attr-defined]
            return True
        return False

    def _should_use_mock_pipeline(self) -> bool:
        if self.remote_inference:
            return True
        if os.getenv("SEIDRA_USE_REAL_MODELS", "0") == "1":
            return False
        if not TORCH_AVAILABLE or not DIFFUSERS_AVAILABLE:
            return True
        if TORCH_AVAILABLE and not torch.cuda.is_available():  # type: ignore[attr-defined]
            return True
        return False

    async def initialize(self):
        if self._initialized:
            return

        print("🔄 Initializing Model Manager...")
        if self.remote_inference:
            print("🌐 Using remote inference endpoints (ComfyUI/SadTalker)")
        else:  # pragma: no cover - requires CUDA environment
            device_name = torch.cuda.get_device_name(0)  # type: ignore[union-attr]
            total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3  # type: ignore[union-attr]
            print(f"✅ GPU detected: {device_name}")
            print(f"💾 VRAM available: {total_mem:.1f}GB")

        await self.load_base_pipeline()
        await self.download_popular_loras()
        self._initialized = True
        self._update_status(initialized=True)
        print("✅ Model Manager initialized")

    async def load_base_pipeline(self):
        if self.remote_inference:
            await self._probe_remote_services()
            self.base_pipeline = None
            self._update_status(current_model="sdxl-base")
            return

        if not DIFFUSERS_AVAILABLE:  # pragma: no cover
            raise RuntimeError("Diffusers not available")

        try:  # pragma: no cover - heavy path
            print("🔄 Loading Stable Diffusion XL pipeline...")
            pipeline = StableDiffusionXLPipeline.from_pretrained(  # type: ignore[operator]
                self.base_models["sdxl-base"],
                torch_dtype=torch.float16,  # type: ignore[arg-type]
                use_safetensors=True,
                variant="fp16",
            )
            pipeline = self.optimizer.optimize_pipeline(pipeline)
            self.base_pipeline = pipeline.to("cuda")
            print("✅ SDXL pipeline loaded and optimized")
            self._update_status(current_model="sdxl-base")
        except Exception as exc:  # pragma: no cover
            print(f"❌ Failed to load base pipeline: {exc}")
            raise

    async def download_popular_loras(self):
        resolved_paths: Dict[str, Path] = {}
        for lora_id, config in self.popular_loras.items():
            asset_config = dict(config)
            asset_config.setdefault("relative_dir", "lora")
            try:
                result = await self.repository.ensure_assets({lora_id: asset_config})
            except DownloadError as exc:
                print(f"⚠️ Failed to prepare {lora_id}: {exc}")
                continue
            resolved_paths.update(result)

        for lora_id, path in resolved_paths.items():
            self.lora_models[lora_id] = {
                "path": str(path),
                "config": self.popular_loras[lora_id],
                "loaded": False,
            }

        self._update_status(available_loras=sorted(self.lora_models.keys()))

    def _should_retry_status(self, status_code: Optional[int]) -> bool:
        if status_code is None:
            return True
        return 500 <= status_code < 600

    def _get_remote_config(self, service: str) -> RemoteServiceSettings:
        return self._remote_settings.for_service(service)

    def _retry_delay(self, attempt: int, config: RemoteServiceSettings) -> float:
        if config.backoff_factor <= 0:
            return 0.0
        return min(
            config.backoff_factor * (2 ** max(attempt - 1, 0)),
            config.backoff_max_seconds,
        )

    async def _execute_with_retries(
        self,
        label: str,
        operation: Callable[[], Awaitable[T]],
        *,
        service: Optional[str] = None,
    ) -> tuple[T, int]:
        last_error: Optional[Exception] = None
        if service:
            try:
                config = self._get_remote_config(service)
            except KeyError:
                config = RemoteServiceSettings()
        else:
            config = RemoteServiceSettings()

        max_attempts = max(1, config.max_attempts)
        for attempt in range(1, max_attempts + 1):
            try:
                result = await operation()
                return result, attempt
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response else None
                if not self._should_retry_status(status_code):
                    raise
                last_error = exc
            except (httpx.RequestError, TimeoutError) as exc:
                last_error = exc

            if attempt < max_attempts:
                delay = self._retry_delay(attempt, config)
                LOGGER.warning(
                    "Nouvelle tentative programmée",
                    extra={
                        "component": "model_manager",
                        "label": label,
                        "service": service,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "delay_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Échec de {label} après {max_attempts} tentatives"
        ) from last_error

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        label: str,
        service: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[httpx.Response, int]:
        async def _operation() -> httpx.Response:
            response = await client.request(method, url, **kwargs)
            if self._should_retry_status(response.status_code):
                response.raise_for_status()
            return response

        response, attempts = await self._execute_with_retries(
            label, _operation, service=service
        )
        response.raise_for_status()
        return response, attempts

    async def _request_json_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        label: str,
        service: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[Dict[str, Any], int]:
        response, attempts = await self._request_with_retries(
            client,
            method,
            url,
            label=label,
            service=service,
            **kwargs,
        )
        return self._parse_json(response, label), attempts

    async def _download_with_retries(
        self,
        client: httpx.AsyncClient,
        url: str,
        destination: Path,
        *,
        label: str,
        service: Optional[str] = None,
    ) -> tuple[Path, int]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_suffix(destination.suffix + ".part")

        async def _operation() -> Path:
            if tmp_path.exists():
                tmp_path.unlink()
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with tmp_path.open("wb") as file_handle:
                    async for chunk in response.aiter_bytes():
                        file_handle.write(chunk)
            tmp_path.replace(destination)
            return destination

        return await self._execute_with_retries(label, _operation, service=service)

    def _parse_json(self, response: httpx.Response, label: str) -> Dict[str, Any]:
        try:
            payload = response.json()
        except Exception as exc:  # pragma: no cover - dépend de la réponse distante
            raise RuntimeError(f"{label} a renvoyé un JSON invalide: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{label} a renvoyé un format inattendu")
        return payload

    async def _record_remote_call_metric(
        self,
        *,
        service: str,
        endpoint: str,
        duration: float,
        success: bool,
        attempts: int,
    ) -> None:
        if not self.telemetry_service:
            return
        queue_length = self._remote_retry_queue.qsize()
        try:
            await self.telemetry_service.record_remote_call(
                service,
                endpoint,
                duration=duration,
                success=success,
                attempts=attempts,
                queue_length=queue_length,
            )
        except Exception:  # pragma: no cover - instrumentation best-effort
            LOGGER.debug("Échec lors de l'envoi des métriques distantes", exc_info=True)

    async def _send_notification(
        self,
        level: str,
        title: str,
        message: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> None:
        if not self.notification_service:
            return
        try:
            await self.notification_service.push(
                level,
                title,
                message,
                category="inference",
                metadata=metadata or {},
                tags=tags or [],
            )
        except Exception:  # pragma: no cover - notification best-effort
            LOGGER.debug("Notification distante impossible à envoyer", exc_info=True)

    async def _handle_remote_failure(
        self,
        *,
        service: str,
        action: str,
        endpoint: str,
        payload: Dict[str, Any],
        media_dir: Path,
        error: Exception,
        metadata: Optional[Dict[str, Any]] = None,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        error_message = str(error)
        from_queue = bool(retry_context and retry_context.get("source") == "queue")
        attempt_index = retry_context.get("attempt") if retry_context else None
        LOGGER.error(
            "Appel distant en échec",
            extra={
                "component": "model_manager",
                "service": service,
                "action": action,
                "endpoint": endpoint,
                "error": error_message,
                "from_queue": from_queue,
                "attempt": attempt_index,
            },
        )
        self.mark_unavailable(error_message)

        if not self.remote_inference:
            return

        base_metadata = {
            "service": service,
            "endpoint": endpoint,
            "action": action,
        }
        if metadata:
            base_metadata.update({k: v for k, v in metadata.items() if v is not None})
        if attempt_index is not None:
            base_metadata["attempt"] = attempt_index

        if from_queue:
            return

        config = self._get_remote_config(service)
        if config.queue_max_retries <= 0:
            await self._send_notification(
                "error",
                f"{service} indisponible",
                f"{action} a échoué: {error_message} (aucune reprise configurée)",
                metadata=base_metadata,
                tags=["remote", service],
            )
            return

        job_metadata = dict(base_metadata)
        job = RemoteRetryJob(
            id=str(uuid.uuid4()),
            service=service,
            action=action,
            payload=copy.deepcopy(payload),
            media_dir=media_dir,
            max_attempts=config.queue_max_retries,
            retry_delay=config.queue_retry_delay_seconds,
            metadata=job_metadata,
        )
        await self._enqueue_remote_job(job)
        await self._send_notification(
            "warning",
            f"{service} en dégradation",
            (
                f"{action} a échoué ({error_message}). "
                f"Relance automatique programmée ({config.queue_max_retries} essais)."
            ),
            metadata=job_metadata,
            tags=["remote", service, "queued"],
        )

    async def _enqueue_remote_job(self, job: RemoteRetryJob) -> None:
        if self._queue_shutdown:
            return
        await self._remote_retry_queue.put(job)
        await self._ensure_retry_worker()
        LOGGER.info(
            "Job distant mis en file d'attente",
            extra={
                "component": "model_manager",
                "service": job.service,
                "action": job.action,
                "job_id": job.id,
                "queue_size": self._remote_retry_queue.qsize(),
                "max_attempts": job.max_attempts,
            },
        )

    async def _ensure_retry_worker(self) -> None:
        if self._queue_worker and not self._queue_worker.done():
            return
        loop = asyncio.get_running_loop()
        self._queue_shutdown = False
        self._queue_worker = loop.create_task(self._retry_worker())

    async def _retry_worker(self) -> None:
        LOGGER.info("Démarrage du worker de reprise distante", extra={"component": "model_manager"})
        try:
            while True:
                job = await self._remote_retry_queue.get()
                try:
                    if job is self._queue_stop_sentinel:
                        break
                    if not isinstance(job, RemoteRetryJob):
                        continue
                    await self._process_retry_job(job)
                finally:
                    self._remote_retry_queue.task_done()
        except asyncio.CancelledError:  # pragma: no cover - arrêt explicite
            LOGGER.info("Worker de reprise distante annulé", extra={"component": "model_manager"})
            raise
        finally:
            LOGGER.info("Arrêt du worker de reprise distante", extra={"component": "model_manager"})

    async def _process_retry_job(self, job: RemoteRetryJob) -> None:
        job.attempts += 1
        LOGGER.info(
            "Relance d'un job distant",
            extra={
                "component": "model_manager",
                "service": job.service,
                "action": job.action,
                "job_id": job.id,
                "attempt": job.attempts,
                "max_attempts": job.max_attempts,
            },
        )

        retry_context = {
            "source": "queue",
            "job_id": job.id,
            "attempt": job.attempts,
        }

        try:
            if job.action == "comfyui.generate_image":
                await self._generate_image_remote(
                    prompt=job.payload.get("prompt", ""),
                    negative_prompt=job.payload.get("negative_prompt", ""),
                    width=job.payload.get("width", 1024),
                    height=job.payload.get("height", 1024),
                    num_inference_steps=job.payload.get("num_inference_steps", 30),
                    guidance_scale=job.payload.get("guidance_scale", 7.5),
                    lora_models=job.payload.get("lora_models"),
                    lora_weights=job.payload.get("lora_weights"),
                    model_name=job.payload.get("model_name", "sdxl-base"),
                    media_dir=job.media_dir,
                    retry_context=retry_context,
                )
            elif job.action == "sadtalker.generate_video":
                await self._generate_video_remote(
                    prompt=job.payload.get("prompt", ""),
                    reference_image=job.payload.get("reference_image"),
                    audio_path=job.payload.get("audio_path"),
                    audio_artifact=job.payload.get("audio_artifact"),
                    duration_seconds=job.payload.get("duration_seconds", 6),
                    model_name=job.payload.get("model_name", "sadtalker"),
                    media_dir=job.media_dir,
                    retry_context=retry_context,
                )
            else:
                raise RuntimeError(f"Action inconnue pour reprise: {job.action}")
        except Exception as exc:
            job.last_error = str(exc)
            remaining = job.max_attempts - job.attempts
            if self._queue_shutdown:
                LOGGER.warning(
                    "Arrêt demandé, abandon du job distant",
                    extra={
                        "component": "model_manager",
                        "service": job.service,
                        "action": job.action,
                        "job_id": job.id,
                        "error": job.last_error,
                    },
                )
                return
            if remaining > 0:
                await self._send_notification(
                    "warning",
                    f"Reprise {job.service} en attente",
                    (
                        f"{job.action} a encore échoué ({job.last_error}). "
                        f"Nouvelle tentative dans {job.retry_delay:.1f}s (reste {remaining})."
                    ),
                    metadata=job.metadata,
                    tags=["remote", job.service, "retry"],
                )
                await asyncio.sleep(job.retry_delay)
                await self._remote_retry_queue.put(job)
            else:
                await self._send_notification(
                    "error",
                    f"Abandon du job {job.service}",
                    f"{job.action} a échoué définitivement: {job.last_error}",
                    metadata=job.metadata,
                    tags=["remote", job.service, "failed"],
                )
                LOGGER.error(
                    "Job distant abandonné",
                    extra={
                        "component": "model_manager",
                        "service": job.service,
                        "action": job.action,
                        "job_id": job.id,
                        "error": job.last_error,
                    },
                )
        else:
            await self._send_notification(
                "info",
                f"Reprise {job.service} réussie",
                f"{job.action} a été rejoué avec succès après {job.attempts} tentative(s)",
                metadata=job.metadata,
                tags=["remote", job.service, "resolved"],
            )
            self.mark_available()

    async def _shutdown_retry_queue(self) -> None:
        self._queue_shutdown = True
        if self._queue_worker and not self._queue_worker.done():
            await self._remote_retry_queue.put(self._queue_stop_sentinel)
            try:
                await self._queue_worker
            except asyncio.CancelledError:  # pragma: no cover - arrêt explicite
                pass
        self._queue_worker = None

    async def load_lora_weights(self, lora_ids: List[str], weights: Optional[List[float]] = None):
        if not self.base_pipeline:
            raise RuntimeError("Base pipeline not loaded")

        if not lora_ids:
            return

        if self.remote_inference:
            self._update_status(loras_loaded=lora_ids)
            return

        if weights is None:
            weights = [1.0] * len(lora_ids)

        try:  # pragma: no cover - heavy path
            self.base_pipeline.unload_lora_weights()
            lora_paths = [self.lora_models[lora_id]["path"] for lora_id in lora_ids if lora_id in self.lora_models]
            if lora_paths:
                # Simplified loading (single LoRA)
                self.base_pipeline.load_lora_weights(lora_paths[0])
                print(f"✅ Loaded LoRA weights: {lora_ids}")
        except Exception as exc:
            print(f"⚠️ Failed to load LoRA weights: {exc}")
        finally:
            self._update_status(loras_loaded=lora_ids)

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
        lora_models: Optional[List[str]] = None,
        lora_weights: Optional[List[float]] = None,
        model_name: str = "sdxl-base",
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        if not self.base_pipeline and not self.remote_inference:
            raise RuntimeError("Pipeline not initialized")

        if lora_models:
            await self.load_lora_weights(lora_models, lora_weights)

        metadata_context: Dict[str, Any] = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "lora_models": lora_models or [],
            "lora_weights": lora_weights or [],
        }
        metrics_context = self._start_generation_metrics(
            media_type="image",
            model_name=model_name,
            metadata=metadata_context,
        )

        output_paths: List[str] = []
        media_dir = settings.media_directory
        media_dir.mkdir(parents=True, exist_ok=True)

        await self._notify_progress(progress_callback, 0.1, "Preparing diffusion pipeline")

        if self.remote_inference:
            await self._notify_progress(progress_callback, 0.25, "Submitting prompt to ComfyUI")
            paths, remote_metadata = await self._generate_image_remote(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                lora_models=lora_models,
                lora_weights=lora_weights,
                model_name=model_name,
                media_dir=media_dir,
            )
            await self._notify_progress(progress_callback, 0.9, "Images downloaded from ComfyUI")
            metrics = self._finalize_generation_metrics(
                metrics_context,
                outputs=len(paths),
                extra={
                    "implementation": "comfyui",
                    "remote_metadata": remote_metadata,
                },
            )
            self._last_generation_metrics = metrics
            self._update_status(
                last_generation={
                    "model": model_name,
                    "loras": lora_models or [],
                    "prompt": prompt,
                    "created_at": datetime.now(UTC).isoformat(),
                    "type": "image",
                    "metadata": remote_metadata,
                },
                loras_loaded=lora_models or [],
            )
            return paths

        # Real generation path (not executed in tests)
        if TORCH_AVAILABLE:  # pragma: no cover - heavy path
            autocast_context = torch.cuda.amp.autocast()
        else:  # pragma: no cover - ensure context manager exists
            from contextlib import nullcontext

            autocast_context = nullcontext()

        try:  # pragma: no cover - heavy path
            with autocast_context:
                result = self.base_pipeline(  # type: ignore[operator]
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    num_images_per_prompt=1,
                )
        except Exception as exc:
            print(f"❌ Generation failed: {exc}")
            raise

        for index, image in enumerate(result.images):  # type: ignore[attr-defined]
            filename = f"generated_{int(time.time()*1000)}_{index}.png"
            output_path = media_dir / filename
            image.save(output_path)
            output_paths.append(str(output_path))
            await self._notify_progress(progress_callback, 0.7 + 0.2 * (index + 1) / len(result.images), "Image rendered")

        metrics = self._finalize_generation_metrics(
            metrics_context,
            outputs=len(output_paths),
            extra={"implementation": "diffusers"},
        )
        self._last_generation_metrics = metrics

        self._update_status(last_generation={
            "model": model_name,
            "loras": lora_models or [],
            "prompt": prompt,
            "created_at": datetime.now(UTC).isoformat(),
            "type": "image",
        })
        return output_paths

    async def _generate_image_remote(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        num_inference_steps: int,
        guidance_scale: float,
        lora_models: Optional[List[str]],
        lora_weights: Optional[List[float]],
        model_name: str,
        media_dir: Path,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[str], Dict[str, Any]]:
        if not settings.comfyui_url:
            raise RuntimeError("ComfyUI endpoint not configured")

        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": num_inference_steps,
            "guidance_scale": guidance_scale,
            "lora_models": lora_models or [],
            "lora_weights": lora_weights or [],
            "model_name": model_name,
        }

        endpoint = self._comfyui_endpoint("api/generate")
        attempts = 0
        success = False
        start_time = time.perf_counter()
        try:
            async with self._create_http_client(service="comfyui") as client:
                data, attempts = await self._request_json_with_retries(
                    client,
                    "POST",
                    endpoint,
                    label="ComfyUI.generate",
                    service="comfyui",
                    json=payload,
                )

                images: List[Dict[str, Any]] = data.get("images", [])
                if not images:
                    raise RuntimeError("ComfyUI response did not include any images")

                saved_paths: List[str] = []
                for index, item in enumerate(images):
                    filename = item.get("filename") or f"comfyui_{int(time.time()*1000)}_{index}.png"
                    output_path = media_dir / filename
                    await self._persist_remote_payload(
                        client,
                        item,
                        output_path,
                        base_url=settings.comfyui_url,
                        service="comfyui",
                    )
                    saved_paths.append(str(output_path))

            metadata = data.get("metadata", {})
            success = True
            return saved_paths, metadata if isinstance(metadata, dict) else {}
        except Exception as exc:
            if attempts == 0:
                attempts = 1
            await self._handle_remote_failure(
                service="comfyui",
                action="comfyui.generate_image",
                endpoint=endpoint,
                payload=payload,
                media_dir=media_dir,
                error=exc,
                metadata={"model_name": model_name, "prompt": prompt},
                retry_context=retry_context,
            )
            raise
        finally:
            duration = time.perf_counter() - start_time
            await self._record_remote_call_metric(
                service="comfyui",
                endpoint="/api/generate",
                duration=duration,
                success=success,
                attempts=attempts,
            )

    async def generate_video(
        self,
        prompt: str,
        reference_image: Optional[str] = None,
        audio_path: Optional[str] = None,
        audio_artifact: Optional[Dict[str, Any]] = None,
        duration_seconds: int = 6,
        model_name: str = "sadtalker",
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        metadata_context: Dict[str, Any] = {
            "prompt": prompt,
            "reference_image": reference_image,
            "audio_path": audio_path,
            "duration_seconds": duration_seconds,
        }
        if audio_artifact:
            metadata_context["audio_artifact"] = {
                "encoding": audio_artifact.get("encoding", "base64"),
                "content_type": audio_artifact.get("content_type"),
                "filename": audio_artifact.get("filename"),
            }
        metrics_context = self._start_generation_metrics(
            media_type="video",
            model_name=model_name,
            metadata=metadata_context,
        )

        media_dir = settings.media_directory
        media_dir.mkdir(parents=True, exist_ok=True)

        await self._notify_progress(progress_callback, 0.05, "Preparing video pipeline")

        outputs = await self._generate_video_remote(
            prompt=prompt,
            reference_image=reference_image,
            audio_path=audio_path,
            audio_artifact=audio_artifact,
            duration_seconds=duration_seconds,
            model_name=model_name,
            media_dir=media_dir,
        )

        await self._notify_progress(progress_callback, 0.85, "Video downloaded from SadTalker")

        metrics = self._finalize_generation_metrics(
            metrics_context,
            outputs=len(outputs),
            extra={
                "implementation": "sadtalker",
                "remote_metadata": {
                    "model_response_count": len(outputs),
                },
            },
        )
        self._last_generation_metrics = metrics

        self._update_status(last_generation={
            "model": model_name,
            "prompt": prompt,
            "reference": reference_image,
            "created_at": datetime.now(UTC).isoformat(),
            "type": "video",
        })

        return outputs

    async def _generate_video_remote(
        self,
        *,
        prompt: str,
        reference_image: Optional[str],
        audio_path: Optional[str],
        audio_artifact: Optional[Dict[str, Any]],
        duration_seconds: int,
        model_name: str,
        media_dir: Path,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        if not settings.sadtalker_url:
            raise RuntimeError("SadTalker endpoint not configured")

        payload = {
            "prompt": prompt,
            "reference_image": reference_image,
            "duration_seconds": duration_seconds,
            "model_name": model_name,
        }

        audio_bytes: Optional[bytes] = None
        audio_filename = None
        audio_content_type = None

        if audio_artifact:
            audio_filename = audio_artifact.get("filename") or None
            audio_content_type = audio_artifact.get("content_type") or None
            data = audio_artifact.get("data")
            if data:
                encoding = (audio_artifact.get("encoding") or "base64").lower()
                if encoding == "base64":
                    try:
                        audio_bytes = base64.b64decode(data)
                    except Exception as exc:  # pragma: no cover - defensive guard
                        raise RuntimeError(f"Invalid base64 audio artifact: {exc}") from exc
                elif isinstance(data, (bytes, bytearray)):
                    audio_bytes = bytes(data)
                elif isinstance(data, str):
                    audio_bytes = data.encode("utf-8")

        if audio_bytes is None and audio_path:
            path_obj = Path(audio_path)
            if not path_obj.exists():
                raise RuntimeError(f"Audio file not found at {audio_path}")
            audio_bytes = path_obj.read_bytes()
            audio_filename = audio_filename or path_obj.name
            if not audio_content_type:
                guessed_type, _ = mimetypes.guess_type(str(path_obj))
                audio_content_type = guessed_type

        if audio_bytes is None:
            raise RuntimeError("Audio data is required for SadTalker video generation")

        if not audio_filename:
            audio_filename = "audio_input.wav"

        if not audio_content_type:
            guessed_type, _ = mimetypes.guess_type(audio_filename)
            audio_content_type = guessed_type or "application/octet-stream"

        form_data = {}
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, (int, float)):
                form_data[key] = str(value)
            else:
                form_data[key] = value

        endpoint = self._sadtalker_endpoint("api/generate")
        attempts = 0
        success = False
        start_time = time.perf_counter()
        try:
            async with self._create_http_client(service="sadtalker") as client:
                data, attempts = await self._request_json_with_retries(
                    client,
                    "POST",
                    endpoint,
                    label="SadTalker.generate",
                    service="sadtalker",
                    data=form_data,
                    files={
                        "audio_file": (audio_filename, audio_bytes, audio_content_type),
                    },
                )

                videos: List[Dict[str, Any]] = data.get("videos", [])
                if not videos:
                    raise RuntimeError("SadTalker response did not include any videos")

                saved_paths: List[str] = []
                for index, item in enumerate(videos):
                    filename = item.get("filename") or f"sadtalker_{int(time.time()*1000)}_{index}.mp4"
                    output_path = media_dir / filename
                    await self._persist_remote_payload(
                        client,
                        item,
                        output_path,
                        base_url=settings.sadtalker_url,
                        service="sadtalker",
                    )
                    saved_paths.append(str(output_path))

            success = True
            return saved_paths
        except Exception as exc:
            if attempts == 0:
                attempts = 1
            await self._handle_remote_failure(
                service="sadtalker",
                action="sadtalker.generate_video",
                endpoint=endpoint,
                payload={
                    "prompt": prompt,
                    "reference_image": reference_image,
                    "duration_seconds": duration_seconds,
                    "model_name": model_name,
                    "audio_artifact": audio_artifact,
                    "audio_path": audio_path,
                },
                media_dir=media_dir,
                error=exc,
                metadata={
                    "model_name": model_name,
                    "prompt": prompt,
                    "reference_image": reference_image,
                },
                retry_context=retry_context,
            )
            raise
        finally:
            duration = time.perf_counter() - start_time
            await self._record_remote_call_metric(
                service="sadtalker",
                endpoint="/api/generate",
                duration=duration,
                success=success,
                attempts=attempts,
            )

    async def get_model_info(self) -> Dict[str, Any]:
        gpu_info: Dict[str, Any] = {}
        if GPUTIL_AVAILABLE:  # pragma: no cover - requires GPU
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    gpu_info = {
                        "name": gpu.name,
                        "memory_total": f"{gpu.memoryTotal}MB",
                        "memory_used": f"{gpu.memoryUsed}MB",
                        "memory_free": f"{gpu.memoryFree}MB",
                        "utilization": f"{gpu.load * 100:.1f}%",
                        "temperature": f"{gpu.temperature}°C",
                    }
            except Exception:
                gpu_info = {}

        if self.remote_inference:
            mode = "remote"
        elif self.use_mock_pipeline:
            mode = "mock"
        else:
            mode = "cuda"

        return {
            "base_pipeline_loaded": self.base_pipeline is not None,
            "available_loras": list(self.lora_models.keys()),
            "gpu_info": gpu_info,
            "optimal_batch_size": self.optimizer.get_optimal_batch_size(),
            "mode": mode,
        }

    def get_last_generation_metrics(self, *, reset: bool = False) -> Optional[Dict[str, Any]]:
        metrics = self._last_generation_metrics
        if reset:
            self._last_generation_metrics = None
        return metrics

    def _start_generation_metrics(
        self,
        *,
        media_type: str,
        model_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "media_type": media_type,
            "model_name": model_name,
            "metadata": metadata or {},
            "started_at": time.perf_counter(),
            "vram_before": self._capture_vram_snapshot(reset_peak=True),
        }

    def _finalize_generation_metrics(
        self,
        context: Dict[str, Any],
        *,
        outputs: int,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if TORCH_AVAILABLE and torch.cuda.is_available():  # pragma: no cover - gpu path
            try:
                torch.cuda.synchronize()  # type: ignore[attr-defined]
            except Exception:
                pass

        duration = max(time.perf_counter() - context.get("started_at", 0.0), 0.0)
        after_snapshot = self._capture_vram_snapshot()
        before_snapshot = context.get("vram_before", {})

        before_alloc = before_snapshot.get("allocated_bytes")
        after_alloc = after_snapshot.get("allocated_bytes")
        vram_delta_mb: Optional[float] = None
        if before_alloc is not None and after_alloc is not None:
            vram_delta_mb = (after_alloc - before_alloc) / (1024 ** 2)

        throughput = None
        if duration > 0 and outputs:
            throughput = outputs / duration

        metadata = dict(context.get("metadata", {}))
        if extra:
            metadata.update(extra)

        metrics = {
            "media_type": context.get("media_type"),
            "model_name": context.get("model_name"),
            "outputs": outputs,
            "duration_seconds": duration,
            "throughput": throughput,
            "vram_allocated_mb": after_snapshot.get("allocated_mb"),
            "vram_reserved_mb": after_snapshot.get("reserved_mb"),
            "vram_peak_mb": after_snapshot.get("peak_mb"),
            "vram_delta_mb": vram_delta_mb,
            "extra": metadata,
            "captured_at": datetime.now(UTC).isoformat(),
        }
        return metrics

    def _capture_vram_snapshot(self, *, reset_peak: bool = False) -> Dict[str, Optional[float]]:
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return {
                "allocated_bytes": None,
                "reserved_bytes": None,
                "peak_bytes": None,
                "allocated_mb": None,
                "reserved_mb": None,
                "peak_mb": None,
            }

        try:  # pragma: no cover - requires CUDA
            device_index = torch.cuda.current_device()
            if reset_peak:
                torch.cuda.reset_peak_memory_stats(device_index)  # type: ignore[attr-defined]
            torch.cuda.synchronize(device_index)  # type: ignore[attr-defined]
            allocated = torch.cuda.memory_allocated(device_index)  # type: ignore[attr-defined]
            reserved = torch.cuda.memory_reserved(device_index)  # type: ignore[attr-defined]
            peak = torch.cuda.max_memory_allocated(device_index)  # type: ignore[attr-defined]
        except Exception:
            return {
                "allocated_bytes": None,
                "reserved_bytes": None,
                "peak_bytes": None,
                "allocated_mb": None,
                "reserved_mb": None,
                "peak_mb": None,
            }

        return {
            "allocated_bytes": float(allocated),
            "reserved_bytes": float(reserved),
            "peak_bytes": float(peak),
            "allocated_mb": float(allocated) / (1024 ** 2),
            "reserved_mb": float(reserved) / (1024 ** 2),
            "peak_mb": float(peak) / (1024 ** 2),
        }

    def get_status_snapshot(self) -> Dict[str, Any]:
        snapshot = dict(self.status)
        snapshot.setdefault("available_loras", list(self.lora_models.keys()))
        return snapshot

    def mark_unavailable(self, reason: str) -> None:
        self._last_known_mode = self.status.get("mode", self._last_known_mode)
        self._update_status(mode="degraded", health="degraded", last_error=reason)

    def mark_available(self) -> None:
        if self.remote_inference:
            target_mode = "remote"
        else:
            target_mode = "mock" if self.use_mock_pipeline else "cuda"
        self._update_status(mode=target_mode, health="healthy", last_error=None)

    async def cleanup(self):
        await self._shutdown_retry_queue()
        if self.base_pipeline and not self.remote_inference and TORCH_AVAILABLE:  # pragma: no cover
            del self.base_pipeline
            torch.cuda.empty_cache()
        self.base_pipeline = None
        self._initialized = False
        self._update_status(initialized=False)
        print("✅ Model Manager cleaned up")

    async def _persist_remote_payload(
        self,
        client: httpx.AsyncClient,
        payload: Dict[str, Any],
        destination: Path,
        *,
        base_url: str,
        service: Optional[str] = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if "data" in payload:
            try:
                binary = base64.b64decode(payload["data"])
            except Exception as exc:  # pragma: no cover - defensive guard
                raise RuntimeError(f"Invalid base64 payload: {exc}") from exc
            destination.write_bytes(binary)
            return

        url = payload.get("url")
        if not url:
            raise RuntimeError("Remote payload is missing both 'url' and 'data'")

        resolved_url = self._resolve_remote_url(base_url, url)
        await self._download_with_retries(
            client,
            resolved_url,
            destination,
            label=f"download:{destination.name}",
            service=service,
        )

    def _resolve_remote_url(self, base_url: str, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not base_url:
            return path
        base = base_url.rstrip("/") + "/"
        return urljoin(base, path.lstrip("/"))

    def _comfyui_endpoint(self, route: str) -> str:
        if not settings.comfyui_url:
            raise RuntimeError("ComfyUI endpoint not configured")
        base = settings.comfyui_url.rstrip("/") + "/"
        return urljoin(base, route.lstrip("/"))

    def _sadtalker_endpoint(self, route: str) -> str:
        if not settings.sadtalker_url:
            raise RuntimeError("SadTalker endpoint not configured")
        base = settings.sadtalker_url.rstrip("/") + "/"
        return urljoin(base, route.lstrip("/"))

    async def _probe_remote_services(self) -> None:
        services: Dict[str, Any] = {}
        services["comfyui"] = await self._fetch_service_health("comfyui", settings.comfyui_url)
        services["sadtalker"] = await self._fetch_service_health("sadtalker", settings.sadtalker_url)

        self._update_status(remote_services=services)

    async def _fetch_service_health(
        self,
        service: str,
        base_url: Optional[str],
    ) -> Dict[str, Any]:
        if not base_url:
            return {"status": "disabled"}

        health_url = self._resolve_remote_url(base_url, "health")
        try:
            async with self._create_http_client(service=service) as client:
                response, _ = await self._request_with_retries(
                    client,
                    "GET",
                    health_url,
                    label=f"health:{base_url}",
                    service=service,
                )
                if response.status_code == 404:
                    return {"status": "unknown"}
                payload = response.json()
                status = payload.get("status", "ok") if isinstance(payload, dict) else "ok"
                return {"status": status, "details": payload}
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}

    async def _notify_progress(self, callback: ProgressCallback, progress: float, message: str) -> None:
        if callback is None:
            return
        try:
            await callback(progress, message)
        except Exception as exc:  # pragma: no cover - defensive logging only
            print(f"⚠️ Progress callback failed: {exc}")

    def _update_status(self, **fields: Any) -> None:
        self.status.update(fields)
        self.status["last_update"] = datetime.now(UTC).isoformat()
