"""
Central generation service orchestrating job lifecycle for SEIDRA Ultimate.

Highlights:
* Maintains realtime vs batch priority queues for deterministic scheduling.
* Persists a local fallback queue when the external broker is unavailable so
  jobs submitted via the API are not perdus en cas de panne.
* Provides a single implementation that can be reused by FastAPI background
  tasks and Celery workers while supporting mock generation for local
  development.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from core.config import settings
from services.database import DatabaseService
from services.model_manager import ModelManager
from services.notifications import NotificationService
from services.websocket_manager import WebSocketManager
from services.telemetry_service import TelemetryService


logger = logging.getLogger(__name__)


class GPUUnavailableError(RuntimeError):
    """Raised when the GPU is temporarily unavailable for generation."""


QueueTag = Literal["realtime", "batch"]
PriorityItem = Tuple[int, float, int, str, Dict[str, Any], str]


class GenerationService:
    GPU_TIMEOUT_SECONDS: float = 90.0
    DEGRADED_BACKOFF_SECONDS: float = 60.0
    NOTIFICATION_PURGE_INTERVAL_SECONDS: int = 3600
    CRITICAL_NOTIFICATION_LEVELS: Tuple[str, ...] = ("error", "critical")
    PRIORITY_MAP: Dict[str, int] = {
        "realtime": 0,
        "high": 1,
        "normal": 5,
        "batch": 9,
        "low": 9,
    }
    QUEUE_TAG_BY_PRIORITY: Dict[str, QueueTag] = {
        "realtime": "realtime",
        "high": "realtime",
        "normal": "realtime",
        "batch": "batch",
        "low": "batch",
    }
    DEGRADED_MODES: Tuple[str, ...] = ("degraded", "offline", "unavailable", "maintenance")
    DEGRADED_HEALTH_STATES: Tuple[str, ...] = ("degraded", "unhealthy", "error")

    def __init__(
        self,
        model_manager: Optional[ModelManager] = None,
        websocket_manager: Optional[WebSocketManager] = None,
        notification_service: Optional[NotificationService] = None,
        telemetry_service: Optional[TelemetryService] = None,
    ):
        self.model_manager = model_manager or ModelManager()
        self.websocket_manager = websocket_manager or WebSocketManager()
        self.notification_service = notification_service
        self.telemetry_service = telemetry_service
        self._initialized = False
        self._initializing_lock = asyncio.Lock()
        self._priority_queues: Dict[QueueTag, "asyncio.PriorityQueue[PriorityItem]"] = {
            "realtime": asyncio.PriorityQueue(),
            "batch": asyncio.PriorityQueue(),
        }
        self._queue_sequence = count()
        self._queue_worker_task: Optional[asyncio.Task[None]] = None
        self._queue_worker_lock = asyncio.Lock()
        self._degraded_until: Optional[datetime] = None
        self._degraded_reason: Optional[str] = None
        self._queue_alert_state: Optional[str] = None
        self._notification_purge_task: Optional[asyncio.Task[None]] = None
        self._notification_purge_lock = asyncio.Lock()
        self._proxy_directory = settings.media_directory / "video_proxies"
        self._waveform_directory = settings.media_directory / "waveforms"
        self._video_asset_directory = settings.media_directory / "video_assets"

    async def ensure_initialized(self):
        if self._initialized:
            return
        async with self._initializing_lock:
            if self._initialized:
                return
            await self.model_manager.initialize()
            await self._ensure_notification_purge_task()
            self._initialized = True

    def _ensure_directory(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_proxy_path(self, timeline_id: str) -> Path:
        self._ensure_directory(self._proxy_directory)
        return self._proxy_directory / f"{timeline_id}.webm"

    def _resolve_waveform_path(self, asset_id: str) -> Path:
        self._ensure_directory(self._waveform_directory)
        return self._waveform_directory / f"{asset_id}.json"

    def _resolve_asset_metadata_path(self, asset_id: str) -> Path:
        self._ensure_directory(self._video_asset_directory)
        return self._video_asset_directory / f"{asset_id}.json"

    def _load_asset_metadata(self, asset_id: str) -> Dict[str, Any]:
        metadata_path = self._resolve_asset_metadata_path(asset_id)
        if not metadata_path.exists():
            raise FileNotFoundError(f"Video asset metadata introuvable pour {asset_id}")
        try:
            return json.loads(metadata_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Métadonnées corrompues pour l’asset {asset_id}") from exc

    async def process_job(
        self, job_id: str, request_data: Dict[str, Any], *, priority_tag: str = "realtime"
    ) -> Dict[str, Any]:
        await self.ensure_initialized()

        if "_priority_tag" in request_data:
            priority_tag = request_data.get("_priority_tag", priority_tag)

        db = DatabaseService()
        try:
            job = db.get_job(job_id)
            if not job:
                raise RuntimeError(f"Job {job_id} not found")

            if not self._is_gpu_available():
                reason = self._current_degraded_reason() or "GPU resources temporarily unavailable"
                await self._handle_gpu_unavailable(job_id, job, reason, priority_tag, db)
                raise GPUUnavailableError(reason)

            job = db.update_job(job_id, status="processing", progress=0.01, error_message=None)

            await self.websocket_manager.send_generation_progress(
                job_id,
                0.05,
                job.user_id,
                "processing",
                "Loading AI models...",
                metadata={
                    "jobType": job.job_type,
                    "modelName": job.model_name,
                    "prompt": job.prompt,
                    "priority": priority_tag,
                    "createdAt": job.created_at.isoformat(),
                },
            )

            prompt = request_data.get("prompt", "")
            negative_prompt = request_data.get("negative_prompt", "")
            width = request_data.get("width", 1024)
            height = request_data.get("height", 1024)
            num_inference_steps = request_data.get("num_inference_steps", 30)
            guidance_scale = request_data.get("guidance_scale", 7.5)
            lora_models = request_data.get("lora_models", [])
            lora_weights = request_data.get("lora_weights")
            seed = request_data.get("seed")
            model_name = request_data.get("model_name", "sdxl-base")
            scheduler = request_data.get("scheduler", "ddim")
            quality = request_data.get("quality", "high")
            style = request_data.get("style")
            job_type = request_data.get("job_type", "image")

            async def _progress(progress: float, message: str) -> None:
                nonlocal job
                updated = db.update_job(job_id, progress=max(min(progress, 0.99), 0.0))
                if updated:
                    job = updated
                await self.websocket_manager.send_generation_progress(
                    job_id,
                    progress,
                    job.user_id,
                    status="processing",
                    message=message,
                    metadata={
                        "jobType": job.job_type,
                        "modelName": job.model_name,
                        "prompt": prompt,
                        "createdAt": job.created_at.isoformat(),
                    },
                )

            await _progress(0.1, "Preparing diffusion pipeline")

            try:
                result_images = await asyncio.wait_for(
                    self.model_manager.generate_image(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        width=width,
                        height=height,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        lora_models=lora_models,
                        lora_weights=lora_weights,
                        model_name=model_name,
                        progress_callback=_progress,
                    ),
                    timeout=self.GPU_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                reason = "GPU inference timeout"
                await self._handle_gpu_unavailable(job_id, job, reason, priority_tag, db)
                raise GPUUnavailableError(reason) from exc
            except Exception as exc:
                if (not self.model_manager.use_mock_pipeline) and self._is_gpu_failure(exc):
                    reason = str(exc) or "GPU failure"
                    await self._handle_gpu_unavailable(job_id, job, reason, priority_tag, db)
                    raise GPUUnavailableError(reason) from exc
                raise

            self._clear_degraded_mode()

            media_items = []
            job_metadata = job.metadata_payload or {}
            for image_path in result_images:
                media_id = str(uuid.uuid4())
                thumbnail_path = image_path.replace(".png", "_thumb.png")
                media_item = db.create_media_item(
                    id=media_id,
                    user_id=job.user_id,
                    job_id=job_id,
                    file_path=image_path,
                    thumbnail_path=thumbnail_path,
                    file_type="image" if job_type == "image" else job_type,
                    mime_type="image/png",
                    metadata={
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "width": width,
                        "height": height,
                        "num_inference_steps": num_inference_steps,
                        "guidance_scale": guidance_scale,
                        "lora_models": lora_models,
                        "seed": seed,
                        "model_name": model_name,
                        "scheduler": scheduler,
                        "quality": quality,
                        "style": style,
                        "generation_time": datetime.utcnow().isoformat(),
                        **job_metadata,
                    },
                )
                media_items.append(media_item)
                self._queue_thumbnail(image_path)

            await _progress(0.95, "Persisting results")

            db.update_job(
                job_id,
                status="completed",
                progress=1.0,
                result_images=result_images,
                metadata={**job_metadata, "scheduler": scheduler, "quality": quality, "style": style},
                completed_at=datetime.utcnow(),
            )

            completion_metadata = {
                "numImages": len(result_images),
                "generationTimeSeconds": (datetime.utcnow() - job.created_at).total_seconds(),
                "prompt": prompt,
                "jobType": job.job_type,
                "modelName": job.model_name,
            }

            await self.websocket_manager.send_generation_complete(
                job_id,
                result_images,
                job.user_id,
                metadata=completion_metadata,
            )

            await self._emit_notification(
                "success",
                "Generation completed",
                f"Job {job_id[:8]} finished with {len(result_images)} image(s).",
                category="jobs",
                metadata={"jobId": job_id, **completion_metadata},
            )

            await self._record_generation_metric(
                job,
                prompt=prompt,
                outputs=len(result_images),
                extra={
                    "seed": seed,
                    "scheduler": scheduler,
                    "quality": quality,
                    "style": style,
                    "negativePromptLength": len(negative_prompt or ""),
                    "requestedLoras": lora_models or [],
                    "priorityTag": priority_tag,
                },
            )

            return {
                "job_id": job_id,
                "status": "completed",
                "result_images": result_images,
                "num_images": len(result_images),
            }
        except GPUUnavailableError:
            raise
        except Exception as exc:
            db.update_job(
                job_id,
                status="failed",
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            )
            self.model_manager.get_last_generation_metrics(reset=True)
            user_id = job.user_id if "job" in locals() and job else 1
            await self.websocket_manager.send_generation_error(job_id, str(exc), user_id)
            await self._emit_notification(
                "error",
                "Generation failed",
                f"Job {job_id[:8]} failed: {exc}",
                category="jobs",
                metadata={"jobId": job_id},
            )
            raise
        finally:
            db.close()

    def _is_gpu_failure(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return any(keyword in message for keyword in ("cuda", "gpu", "cublas", "torch", "device"))

    async def _handle_gpu_unavailable(
        self,
        job_id: str,
        job: Any,
        reason: str,
        priority_tag: str,
        db: DatabaseService,
    ) -> None:
        self._enter_degraded_mode(reason)
        retry_after = int(self.DEGRADED_BACKOFF_SECONDS)
        metadata = dict(job.metadata_payload or {})
        degraded_info = metadata.get("degraded")
        if not isinstance(degraded_info, dict):
            degraded_info = {}
        history = list(degraded_info.get("history", []))
        history.append({"timestamp": datetime.utcnow().isoformat(), "reason": reason})
        degraded_info.update(
            {
                "history": history,
                "retry_after_seconds": retry_after,
                "priority": priority_tag,
            }
        )
        metadata["degraded"] = degraded_info

        updated = db.update_job(
            job_id,
            status="pending",
            progress=0.0,
            error_message=reason,
            metadata=metadata,
        )
        job = updated or job

        logger.warning(
            "Delaying job %s due to GPU unavailability (%s). Retry in %ss.",
            job_id,
            priority_tag,
            retry_after,
        )

        message = (
            f"GPU unavailable: {reason}. Retrying shortly."
            if reason
            else "GPU unavailable. Retrying shortly."
        )
        await self.websocket_manager.send_generation_progress(
            job_id,
            0.0,
            job.user_id,
            status="delayed",
            message=message,
            metadata={
                "jobType": job.job_type,
                "modelName": job.model_name,
                "prompt": job.prompt,
                "priority": priority_tag,
                "retryAfter": retry_after,
                "createdAt": job.created_at.isoformat(),
            },
        )

        await self._emit_notification(
            "warning",
            "GPU temporarily unavailable",
            f"Job {job_id[:8]} delayed: {reason}",
            category="jobs",
            metadata={"jobId": job_id, "retryAfter": retry_after, "priority": priority_tag},
        )

    def _enter_degraded_mode(self, reason: str) -> None:
        if self.model_manager.use_mock_pipeline:
            return
        if reason and reason != self._degraded_reason:
            logger.warning("Entering GPU degraded mode: %s", reason)
        self._degraded_reason = reason
        self._degraded_until = datetime.utcnow() + timedelta(seconds=self.DEGRADED_BACKOFF_SECONDS)
        with suppress(Exception):
            self.model_manager.mark_unavailable(reason)

    def _clear_degraded_mode(self) -> None:
        if self.model_manager.use_mock_pipeline:
            return
        if self._degraded_until is None and self._degraded_reason is None:
            return
        logger.info("GPU resources marked as available again")
        self._degraded_until = None
        self._degraded_reason = None
        with suppress(Exception):
            self.model_manager.mark_available()

    def _current_degraded_reason(self) -> Optional[str]:
        if self._degraded_reason:
            return self._degraded_reason
        snapshot = self.model_manager.get_status_snapshot()
        return snapshot.get("last_error")

    def _is_gpu_available(self) -> bool:
        if self.model_manager.use_mock_pipeline:
            return True

        now = datetime.utcnow()
        if self._degraded_until and now >= self._degraded_until:
            self._clear_degraded_mode()

        if self._degraded_until:
            return False

        snapshot = self.model_manager.get_status_snapshot()
        mode = str(snapshot.get("mode") or "").lower()
        health = str(snapshot.get("health") or "").lower()
        available_flag = snapshot.get("available")
        is_degraded = (
            mode in self.DEGRADED_MODES
            or health in self.DEGRADED_HEALTH_STATES
            or available_flag is False
        )
        if is_degraded:
            if not self._degraded_until:
                self._degraded_until = now + timedelta(seconds=self.DEGRADED_BACKOFF_SECONDS)
                logger.warning(
                    "Model manager reports GPU unavailable (mode=%s, health=%s, available=%s)",
                    mode or None,
                    health or None,
                    available_flag,
                )
            self._degraded_reason = (
                snapshot.get("last_error")
                or snapshot.get("status")
                or snapshot.get("message")
                or self._degraded_reason
            )
            return False
        return True

    @classmethod
    def resolve_priority_queue_tag(cls, priority_tag: str) -> QueueTag:
        normalized = (priority_tag or "normal").lower()
        return cls.QUEUE_TAG_BY_PRIORITY.get(normalized, "realtime")

    def _priority_value(self, priority_tag: str) -> int:
        normalized = (priority_tag or "normal").lower()
        return self.PRIORITY_MAP.get(normalized, self.PRIORITY_MAP["normal"])

    async def enqueue_job(
        self,
        job_id: str,
        request_data: Dict[str, Any],
        *,
        priority_tag: str = "realtime",
        delay_seconds: float = 0.0,
    ) -> None:
        await self._ensure_queue_worker()
        payload = dict(request_data)
        payload.setdefault("_priority_tag", priority_tag)
        loop = asyncio.get_running_loop()
        available_at = loop.time() + max(delay_seconds, 0.0)
        priority_value = self._priority_value(priority_tag)
        queue_tag = self.resolve_priority_queue_tag(priority_tag)
        sequence = next(self._queue_sequence)
        await self._priority_queues[queue_tag].put(
            (priority_value, available_at, sequence, job_id, payload, priority_tag)
        )
        logger.info(
            "Queued job %s with priority %s in %s queue (delay %.2fs)",
            job_id,
            priority_tag,
            queue_tag,
            max(delay_seconds, 0.0),
        )

        await self._maybe_trigger_queue_alert()

    async def _ensure_queue_worker(self) -> None:
        async with self._queue_worker_lock:
            if self._queue_worker_task and not self._queue_worker_task.done():
                return
            loop = asyncio.get_running_loop()
            self._queue_worker_task = loop.create_task(self._queue_worker_loop())

    async def _queue_worker_loop(self) -> None:
        try:
            while True:
                queue_tag, item = await self._await_next_queued_job()
                await self._process_queue_item(queue_tag, item)
        except asyncio.CancelledError:
            logger.info("Generation queue worker cancelled")
            raise

    async def _process_queue_item(self, queue_tag: QueueTag, item: PriorityItem) -> None:
        while True:
            (
                priority,
                available_at,
                _sequence,
                job_id,
                request_data,
                priority_tag,
            ) = item
            loop = asyncio.get_running_loop()
            wait_time = max(0.0, available_at - loop.time())
            logger.debug(
                "Processing queued job %s (queue=%s priority=%d wait=%.3fs)",
                job_id,
                queue_tag,
                priority,
                wait_time,
            )
            if wait_time and queue_tag == "batch":
                realtime_queue = self._priority_queues["realtime"]
                sleep_task = asyncio.create_task(asyncio.sleep(wait_time))
                realtime_task = asyncio.create_task(realtime_queue.get())
                done, pending = await asyncio.wait(
                    {sleep_task, realtime_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if realtime_task in done:
                    for pending_task in pending:
                        pending_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await pending_task
                    realtime_item = realtime_task.result()
                    logger.debug(
                        "Realtime job %s preempted batch job %s", realtime_item[3], job_id
                    )
                    await self._process_queue_item("realtime", realtime_item)
                    continue
                else:
                    realtime_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await realtime_task
                    wait_time = 0.0
                    if not realtime_queue.empty():
                        realtime_item = await realtime_queue.get()
                        logger.debug(
                            "Realtime job %s acquired after wait for %s",
                            realtime_item[3],
                            job_id,
                        )
                        await self._process_queue_item("realtime", realtime_item)
                        continue
            try:
                if wait_time:
                    await asyncio.sleep(wait_time)
                await self.process_job(job_id, request_data, priority_tag=priority_tag)
            except GPUUnavailableError as exc:
                logger.warning(
                    "GPU unavailable while processing queued job %s (%s, %s priority=%d): %s",
                    job_id,
                    priority_tag,
                    queue_tag,
                    priority,
                    exc,
                )
                await self._handle_gpu_delay(job_id, request_data, priority_tag)
            except Exception as exc:
                logger.exception("Job %s failed during local queue processing: %s", job_id, exc)
            finally:
                self._priority_queues[queue_tag].task_done()
                await self._maybe_trigger_queue_alert()
            break

    async def _await_next_queued_job(self) -> Tuple[QueueTag, PriorityItem]:
        realtime_queue = self._priority_queues["realtime"]
        batch_queue = self._priority_queues["batch"]
        try:
            item = realtime_queue.get_nowait()
            return "realtime", item
        except asyncio.QueueEmpty:
            pass
        try:
            item = batch_queue.get_nowait()
            return "batch", item
        except asyncio.QueueEmpty:
            pass

        realtime_task = asyncio.create_task(realtime_queue.get())
        batch_task = asyncio.create_task(batch_queue.get())
        task_map: Dict[asyncio.Task[PriorityItem], QueueTag] = {
            realtime_task: "realtime",
            batch_task: "batch",
        }
        try:
            done, pending = await asyncio.wait(
                task_map.keys(), return_when=asyncio.FIRST_COMPLETED
            )
            completed_task = next(iter(done))
            for pending_task in pending:
                pending_task.cancel()
                with suppress(asyncio.CancelledError):
                    await pending_task
            queue_tag = task_map[completed_task]
            return queue_tag, completed_task.result()
        except asyncio.CancelledError:
            for task in task_map:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            raise
        except Exception:
            for task in task_map:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
            raise

    async def _handle_gpu_delay(
        self, job_id: str, request_data: Dict[str, Any], priority_tag: str
    ) -> None:
        await self.enqueue_job(
            job_id,
            request_data,
            priority_tag=priority_tag,
            delay_seconds=self.DEGRADED_BACKOFF_SECONDS,
        )

    async def process_video_job(self, job_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_initialized()

        db = DatabaseService()
        try:
            job = db.update_job(job_id, status="processing", progress=0.01)
            if not job:
                raise RuntimeError(f"Job {job_id} not found")

            await self.websocket_manager.send_generation_progress(
                job_id,
                0.05,
                job.user_id,
                status="processing",
                message="Initializing video pipeline...",
                metadata={
                    "jobType": job.job_type,
                    "modelName": job.model_name,
                    "prompt": job.prompt,
                    "createdAt": job.created_at.isoformat(),
                },
            )

            prompt = request_data.get("prompt", "")
            reference_image = request_data.get("reference_image") or request_data.get("referenceImage")
            audio_path = request_data.get("audio_path") or request_data.get("audioPath")
            audio_artifact = request_data.get("audio_artifact") or request_data.get("audioArtifact")
            duration = int(request_data.get("duration_seconds", request_data.get("durationSeconds", 6)))
            model_name = request_data.get("model_name", "sadtalker")

            async def _progress(progress: float, message: str) -> None:
                nonlocal job
                updated = db.update_job(job_id, progress=max(min(progress, 0.99), 0.0))
                if updated:
                    job = updated
                await self.websocket_manager.send_generation_progress(
                    job_id,
                    progress,
                    job.user_id,
                    status="processing",
                    message=message,
                    metadata={
                        "jobType": job.job_type,
                        "modelName": job.model_name,
                        "prompt": prompt,
                        "createdAt": job.created_at.isoformat(),
                    },
                )

            await _progress(0.1, "Composing scene")

            outputs = await self.model_manager.generate_video(
                prompt=prompt,
                reference_image=reference_image,
                audio_path=audio_path,
                audio_artifact=audio_artifact,
                duration_seconds=duration,
                model_name=model_name,
                progress_callback=_progress,
            )

            job_metadata = job.metadata_payload or {}
            for path in outputs:
                db.create_media_item(
                    id=str(uuid.uuid4()),
                    user_id=job.user_id,
                    job_id=job_id,
                    file_path=path,
                    file_type="video",
                    mime_type="video/mp4",
                    metadata={
                        "prompt": prompt,
                        "reference_image": reference_image,
                        "audio_path": audio_path,
                        "duration_seconds": duration,
                        **job_metadata,
                    },
                )

            await _progress(0.96, "Finalizing job")

            db.update_job(
                job_id,
                status="completed",
                progress=1.0,
                result_images=outputs,
                metadata={**job_metadata, "duration_seconds": duration, "model": model_name},
                completed_at=datetime.utcnow(),
            )

            completion_metadata = {
                "numVideos": len(outputs),
                "generationTimeSeconds": (datetime.utcnow() - job.created_at).total_seconds(),
                "prompt": prompt,
                "jobType": job.job_type,
                "modelName": job.model_name,
            }

            await self.websocket_manager.send_generation_complete(
                job_id,
                outputs,
                job.user_id,
                metadata=completion_metadata,
            )

            await self._emit_notification(
                "success",
                "Video generation completed",
                f"Job {job_id[:8]} finished with {len(outputs)} video(s).",
                category="jobs",
                metadata={"jobId": job_id, **completion_metadata},
            )

            await self._record_generation_metric(
                job,
                prompt=prompt,
                outputs=len(outputs),
                extra={
                    "referenceImage": reference_image,
                    "audioPath": audio_path,
                    "requestedDuration": duration,
                    "priorityTag": request_data.get("_priority_tag") or "batch",
                },
            )

            return {
                "job_id": job_id,
                "status": "completed",
                "result_videos": outputs,
                "num_videos": len(outputs),
            }
        except Exception as exc:
            db.update_job(
                job_id,
                status="failed",
                error_message=str(exc),
                completed_at=datetime.utcnow(),
            )
            self.model_manager.get_last_generation_metrics(reset=True)
            user_id = job.user_id if "job" in locals() and job else 1
            await self.websocket_manager.send_generation_error(job_id, str(exc), user_id)
            await self._emit_notification(
                "error",
                "Video generation failed",
                f"Job {job_id[:8]} failed: {exc}",
                category="jobs",
                metadata={"jobId": job_id},
            )
            raise
        finally:
            db.close()

    async def generate_asset_waveform(
        self,
        asset_id: str,
        *,
        sample_points: int = 128,
        force: bool = False,
    ) -> Dict[str, Any]:
        await self.ensure_initialized()
        return await asyncio.to_thread(
            self._generate_asset_waveform_sync,
            asset_id,
            sample_points,
            force,
        )

    def generate_asset_waveform_sync(
        self, asset_id: str, *, sample_points: int = 128, force: bool = False
    ) -> Dict[str, Any]:
        return self._generate_asset_waveform_sync(asset_id, sample_points, force)

    def _generate_asset_waveform_sync(
        self, asset_id: str, sample_points: int = 128, force: bool = False
    ) -> Dict[str, Any]:
        waveform_path = self._resolve_waveform_path(asset_id)
        if waveform_path.exists() and not force:
            try:
                return json.loads(waveform_path.read_text())
            except json.JSONDecodeError:
                waveform_path.unlink(missing_ok=True)

        metadata = self._load_asset_metadata(asset_id)
        file_path = Path(metadata.get("file_path", ""))
        if not file_path.exists():
            raise FileNotFoundError(
                f"Fichier audio introuvable pour l’asset {asset_id}: {file_path}"
            )

        kind = (metadata.get("kind") or "audio").lower()
        if kind not in {"audio", "video"}:
            raise ValueError(
                f"La génération de waveform est réservée aux assets audio/vidéo (asset={asset_id})"
            )

        import librosa  # type: ignore
        import numpy as np  # type: ignore

        audio, sr = librosa.load(str(file_path), sr=None, mono=True)
        if audio.size == 0:
            raise ValueError(f"Audio vide pour l’asset {asset_id}")

        points = max(int(sample_points), 16)
        window = max(int(len(audio) / points), 1)
        peaks: List[float] = []
        for index in range(points):
            start = index * window
            end = start + window
            segment = audio[start:end]
            if segment.size == 0:
                peaks.append(0.0)
            else:
                peaks.append(float(np.max(np.abs(segment))))

        peak_amplitude = float(np.max(np.abs(audio)))
        normalized = [round(min(peak / peak_amplitude if peak_amplitude else 0.0, 1.0), 4) for peak in peaks]

        payload = {
            "asset_id": asset_id,
            "waveform": normalized,
            "sample_rate": int(sr),
            "peak_amplitude": peak_amplitude,
            "generated_at": datetime.utcnow().isoformat(),
        }

        waveform_path.write_text(json.dumps(payload))
        return payload

    def load_asset_waveform(self, asset_id: str) -> Optional[Dict[str, Any]]:
        waveform_path = self._resolve_waveform_path(asset_id)
        if not waveform_path.exists():
            return None
        try:
            return json.loads(waveform_path.read_text())
        except json.JSONDecodeError:
            waveform_path.unlink(missing_ok=True)
            return None

    async def generate_timeline_proxy(
        self,
        job_id: str,
        timeline_id: str,
        user_id: int,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        await self.ensure_initialized()
        return await asyncio.to_thread(
            self._generate_timeline_proxy_sync,
            job_id,
            timeline_id,
            user_id,
            force,
        )

    def generate_timeline_proxy_sync(
        self,
        job_id: str,
        timeline_id: str,
        user_id: int,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        return self._generate_timeline_proxy_sync(job_id, timeline_id, user_id, force)

    def _generate_timeline_proxy_sync(
        self,
        job_id: str,
        timeline_id: str,
        user_id: int,
        force: bool = False,
    ) -> Dict[str, Any]:
        proxy_path = self._resolve_proxy_path(timeline_id)
        try:
            relative_path = proxy_path.relative_to(settings.media_directory)
        except ValueError:
            relative_path = proxy_path
        relative_url = f"/media/{relative_path.as_posix()}"

        db = DatabaseService()
        try:
            timeline = db.get_video_timeline(timeline_id, user_id)
            if timeline is None:
                raise RuntimeError(f"Timeline {timeline_id} introuvable")

            job = db.get_job(job_id)
            if job:
                db.update_job(job_id, status="processing", progress=0.1)

            timeline_payload = timeline.timeline_payload or {}
            preview_state = (timeline_payload.get("proxy_preview") or {}).copy()

            if proxy_path.exists() and not force:
                now = datetime.utcnow().isoformat()
                preview_state.update(
                    {
                        "status": "ready",
                        "proxy_url": relative_url,
                        "job_id": job_id,
                        "updated_at": now,
                    }
                )
                db.update_video_timeline(
                    timeline_id,
                    user_id,
                    timeline={**timeline_payload, "proxy_preview": preview_state},
                )
                if job:
                    db.update_job(
                        job_id,
                        status="completed",
                        progress=1.0,
                        result_images=[relative_url],
                        completed_at=datetime.utcnow(),
                    )
                return {
                    "timeline_id": timeline_id,
                    "status": "ready",
                    "proxy_url": relative_url,
                    "job_id": job_id,
                    "updated_at": preview_state.get("updated_at"),
                }

            video_asset = self._select_timeline_preview_asset(timeline_payload)

            if video_asset is None:
                self._render_blank_proxy(proxy_path, timeline.total_duration or 5)
            else:
                self._render_asset_proxy(proxy_path, video_asset)

            if not proxy_path.exists():
                raise RuntimeError("La génération du proxy a échoué : fichier absent")

            now = datetime.utcnow().isoformat()
            preview_state.update(
                {
                    "status": "ready",
                    "proxy_url": relative_url,
                    "job_id": job_id,
                    "updated_at": now,
                }
            )
            db.update_video_timeline(
                timeline_id,
                user_id,
                timeline={**timeline_payload, "proxy_preview": preview_state},
            )

            if job:
                db.update_job(
                    job_id,
                    status="completed",
                    progress=1.0,
                    result_images=[relative_url],
                    completed_at=datetime.utcnow(),
                )

            return {
                "timeline_id": timeline_id,
                "status": "ready",
                "proxy_url": relative_url,
                "job_id": job_id,
                "updated_at": now,
            }
        except Exception as exc:
            logger.exception("Échec génération proxy pour timeline %s", timeline_id)
            if job_id:
                db.update_job(
                    job_id,
                    status="failed",
                    error_message=str(exc),
                    completed_at=datetime.utcnow(),
                )
            raise
        finally:
            db.close()

    def _select_timeline_preview_asset(
        self, timeline_payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        assets_payload = timeline_payload.get("assets") or []
        clips_payload = timeline_payload.get("clips") or []
        assets_by_id = {
            asset.get("id"): asset
            for asset in assets_payload
            if isinstance(asset, dict) and asset.get("id")
        }

        video_clips = [
            clip
            for clip in clips_payload
            if isinstance(clip, dict) and clip.get("layer") == "video"
        ]
        video_clips.sort(key=lambda clip: float(clip.get("start", 0)))

        for clip in video_clips:
            asset_id = clip.get("asset_id")
            if not asset_id:
                continue
            metadata = None
            try:
                metadata = self._load_asset_metadata(asset_id)
            except Exception:
                continue

            asset_payload = assets_by_id.get(asset_id) or {}
            kind = (asset_payload.get("kind") or metadata.get("kind") or "video").lower()
            file_path = Path(metadata.get("file_path", ""))
            if not file_path.exists():
                continue
            if kind not in {"video", "image"}:
                continue
            return {
                "asset_id": asset_id,
                "kind": kind,
                "file_path": str(file_path),
                "clip": clip,
            }
        return None

    def _render_asset_proxy(self, proxy_path: Path, asset: Dict[str, Any]) -> None:
        file_path = Path(asset["file_path"])
        kind = asset.get("kind", "video")
        duration = float(asset.get("clip", {}).get("duration") or 5.0)

        command: List[str]
        if kind == "image":
            command = [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(file_path),
                "-t",
                str(max(duration, 1.0)),
                "-vf",
                "scale=640:-2,format=yuv420p",
                "-an",
                "-c:v",
                "libvpx-vp9",
                str(proxy_path),
            ]
        else:
            command = [
                "ffmpeg",
                "-y",
                "-i",
                str(file_path),
                "-vf",
                "scale=640:-2,format=yuv420p",
                "-an",
                "-c:v",
                "libvpx-vp9",
                "-deadline",
                "realtime",
                str(proxy_path),
            ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg a échoué pour {file_path} → {proxy_path}: {result.stderr.decode(errors='ignore')}"
            )

    def _render_blank_proxy(self, proxy_path: Path, duration: float) -> None:
        seconds = max(float(duration), 1.0)
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=640x360:d={seconds}",
            "-vf",
            "drawtext=text='Timeline sans vidéo':fontcolor=white:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2",
            "-an",
            "-c:v",
            "libvpx-vp9",
            str(proxy_path),
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg a échoué pour proxy vierge {proxy_path}: {result.stderr.decode(errors='ignore')}"
            )

    async def notify_job_queued(self, job_id: str):
        db = DatabaseService()
        try:
            job = db.get_job(job_id)
        finally:
            db.close()

        metadata = {
            "jobId": job_id,
            "status": "queued",
            "progress": 0.0,
            "jobType": getattr(job, "job_type", None),
            "modelName": getattr(job, "model_name", None),
            "prompt": getattr(job, "prompt", None),
            "createdAt": job.created_at.isoformat() if job and job.created_at else datetime.utcnow().isoformat(),
        }

        await self.websocket_manager.dispatch_event(
            {
                "type": "job_queued",
                **metadata,
            },
            channels={"jobs"},
            user_id=job.user_id if job else None,
        )

        await self._emit_notification(
            "info",
            "Job queued",
            f"Job {job_id[:8]} queued for processing.",
            category="jobs",
            metadata=metadata,
        )

    async def notify_batch_queued(self, job_ids: List[str]):
        await self.websocket_manager.dispatch_event(
            {
                "type": "batch_queued",
                "jobIds": job_ids,
                "message": f"Batch generation queued ({len(job_ids)} jobs)",
                "timestamp": datetime.utcnow().isoformat(),
            },
            channels={"jobs"},
        )

        await self._emit_notification(
            "info",
            "Batch queued",
            f"Queued {len(job_ids)} job(s) for batch processing.",
            category="jobs",
            metadata={"jobIds": job_ids},
        )

    def process_job_sync(
        self, job_id: str, request_data: Dict[str, Any], *, priority_tag: str = "realtime"
    ) -> Dict[str, Any]:
        return self._run_sync(self.process_job(job_id, request_data, priority_tag=priority_tag))

    def process_video_job_sync(self, job_id: str, request_data: Dict[str, Any]) -> Dict[str, Any]:
        return self._run_sync(self.process_video_job(job_id, request_data))

    def _queue_thumbnail(self, file_path: str) -> None:
        with suppress(Exception):
            from workers.media_worker import generate_thumbnail

            generate_thumbnail.delay(file_path)

    async def _maybe_trigger_queue_alert(self) -> None:
        thresholds = settings.notification_thresholds
        warning_threshold = max(thresholds.queue_warning, 0)
        critical_threshold = max(thresholds.queue_critical, 0)

        if warning_threshold == 0 and critical_threshold == 0:
            return

        realtime_depth = self._priority_queues["realtime"].qsize()
        batch_depth = self._priority_queues["batch"].qsize()
        total_depth = realtime_depth + batch_depth

        severity: Optional[str] = None
        if critical_threshold and total_depth >= critical_threshold:
            severity = "critical"
        elif warning_threshold and total_depth >= warning_threshold:
            severity = "warning"

        if severity is None:
            if self._queue_alert_state is not None:
                await self._emit_notification(
                    "info",
                    "File d'attente stabilisée",
                    "La file d'attente de génération est revenue sous les seuils configurés.",
                    category="system",
                    metadata={
                        "queueDepth": total_depth,
                        "queueRealtime": realtime_depth,
                        "queueBatch": batch_depth,
                    },
                    tags=["queue", "recovery"],
                )
            self._queue_alert_state = None
            return

        if self._queue_alert_state == severity:
            return

        self._queue_alert_state = severity
        threshold_value = (
            critical_threshold if severity == "critical" else warning_threshold
        )
        level = "error" if severity == "critical" else "warning"
        title = (
            "File d'attente saturée"
            if severity == "critical"
            else "File d'attente chargée"
        )
        message = (
            f"Il y a actuellement {total_depth} tâche(s) en attente (seuil {threshold_value})."
        )
        await self._emit_notification(
            level,
            title,
            message,
            category="system",
            metadata={
                "queueDepth": total_depth,
                "queueRealtime": realtime_depth,
                "queueBatch": batch_depth,
                "threshold": threshold_value,
                "severity": severity,
            },
            tags=["queue", severity],
        )

    async def _emit_notification(
        self,
        level: str,
        title: str,
        message: str,
        *,
        category: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[Iterable[str]] = None,
    ) -> None:
        tags_list = list(tags or [])
        if self.notification_service:
            await self.notification_service.push(
                level,
                title,
                message,
                category=category,
                metadata=metadata,
                tags=tags_list,
            )
            return

        if level.lower() not in self.CRITICAL_NOTIFICATION_LEVELS:
            return

        await asyncio.to_thread(
            self._persist_notification,
            level,
            title,
            message,
            category,
            metadata or {},
            tags_list,
        )

    def _persist_notification(
        self,
        level: str,
        title: str,
        message: str,
        category: str,
        metadata: Dict[str, Any],
        tags: List[str],
    ) -> None:
        db = DatabaseService()
        try:
            db.create_notification(
                level=level,
                title=title,
                message=message,
                category=category,
                metadata=metadata,
                tags=tags,
            )
        finally:
            db.close()

    async def _ensure_notification_purge_task(self) -> None:
        retention_days = max(getattr(settings, "notification_retention_days", 0), 0)
        if retention_days == 0:
            return

        async with self._notification_purge_lock:
            if self._notification_purge_task and not self._notification_purge_task.done():
                return
            loop = asyncio.get_running_loop()
            self._notification_purge_task = loop.create_task(self._notification_purge_loop())

    async def _notification_purge_loop(self) -> None:
        interval = max(int(self.NOTIFICATION_PURGE_INTERVAL_SECONDS), 60)
        try:
            while True:
                try:
                    await asyncio.to_thread(self._purge_stale_notifications)
                except Exception:
                    logger.exception("Failed to purge critical notifications")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Notification purge task cancelled")
            raise

    def _purge_stale_notifications(self) -> None:
        retention_days = max(getattr(settings, "notification_retention_days", 0), 0)
        if retention_days == 0:
            return

        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        db = DatabaseService()
        try:
            deleted = db.delete_notifications_older_than(
                cutoff,
                levels=self.CRITICAL_NOTIFICATION_LEVELS,
            )
            if deleted:
                logger.info(
                    "Purged %d critical notifications older than %d day(s)",
                    deleted,
                    retention_days,
                )
        finally:
            db.close()

    async def _record_generation_metric(
        self,
        job: GenerationJob,
        *,
        prompt: str,
        outputs: int,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        metrics_payload = self.model_manager.get_last_generation_metrics(reset=True)
        if not self.telemetry_service or not metrics_payload:
            return

        extra_payload = dict(metrics_payload.get("extra", {}))
        for key, value in (extra or {}).items():
            if value is not None:
                extra_payload[key] = value

        metric_record = {
            "job_id": job.id,
            "user_id": job.user_id,
            "persona_id": job.persona_id,
            "media_type": metrics_payload.get("media_type") or job.job_type,
            "model_name": metrics_payload.get("model_name") or job.model_name,
            "prompt": prompt,
            "outputs": metrics_payload.get("outputs") or outputs,
            "duration_seconds": metrics_payload.get("duration_seconds"),
            "throughput": metrics_payload.get("throughput"),
            "vram_allocated_mb": metrics_payload.get("vram_allocated_mb"),
            "vram_reserved_mb": metrics_payload.get("vram_reserved_mb"),
            "vram_peak_mb": metrics_payload.get("vram_peak_mb"),
            "vram_delta_mb": metrics_payload.get("vram_delta_mb"),
            "extra": extra_payload,
        }

        await self.telemetry_service.record_generation_metric(metric_record)

    def _run_sync(self, coroutine: "asyncio.Future[Any]") -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            return asyncio.run_coroutine_threadsafe(coroutine, loop).result()

        return asyncio.run(coroutine)


_generation_service: Optional[GenerationService] = None


def get_generation_service() -> GenerationService:
    global _generation_service
    if _generation_service is None:
        _generation_service = GenerationService()
    return _generation_service


def configure_generation_service(
    model_manager: ModelManager,
    websocket_manager: WebSocketManager,
    notification_service: Optional[NotificationService] = None,
    telemetry_service: Optional[TelemetryService] = None,
) -> GenerationService:
    service = get_generation_service()
    service.model_manager = model_manager
    service.websocket_manager = websocket_manager
    service.notification_service = notification_service
    service.telemetry_service = telemetry_service
    if settings.notification_retention_days > 0:
        with suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(service._ensure_notification_purge_task())
    return service

    

    
