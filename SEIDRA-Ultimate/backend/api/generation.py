"""
SEIDRA Generation API
Handles image generation requests with RTX 3090 optimization.
Now backed by a shared GenerationService that supports Celery workers and
in-process async execution for local development.
"""

from __future__ import annotations

import os
import base64
import uuid
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from typing import Literal

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Form, UploadFile, File
from pydantic import BaseModel, Field

from api.auth import verify_token
from services.database import DatabaseService
from services.generation_service import get_generation_service
from core.config import settings
from core.rate_limit import generation_rate_limit_dependencies

from workers.generation_worker import (
    submit_batch_generation_job,
    submit_generation_job,
)

from workers.generation_worker import generate_images_task, batch_generate_images_task
from workers.video_worker import (
    generate_asset_waveform_task,
    generate_timeline_proxy_task,
    generate_video_task,
)


router = APIRouter(
    dependencies=[Depends(verify_token), *generation_rate_limit_dependencies]
)
_generation_service = get_generation_service()
USE_CELERY = os.getenv("SEIDRA_USE_CELERY", "0") == "1"


def _resolve_batch_priority(priority: str) -> str:
    normalized = (priority or "normal").lower()
    if normalized in {"realtime", "high"}:
        return "realtime"
    if normalized in {"batch", "low"}:
        return "batch"
    return "batch"


class GenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: str = Field(default="", max_length=2000)
    width: int = Field(default=1024, ge=512, le=2048)
    height: int = Field(default=1024, ge=512, le=2048)
    num_inference_steps: int = Field(default=30, ge=10, le=100)
    guidance_scale: float = Field(default=7.5, ge=1.0, le=20.0)
    num_images: int = Field(default=1, ge=1, le=4)
    persona_id: Optional[int] = None
    lora_models: List[str] = Field(default=[])
    lora_weights: List[float] = Field(default=[])
    seed: Optional[int] = None
    model_name: str = Field(default="sdxl-base")
    scheduler: str = Field(default="ddim")
    style: Optional[str] = Field(default=None)
    quality: str = Field(default="high")
    is_nsfw: bool = Field(default=False)
    job_type: str = Field(default="image")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BatchGenerationRequest(BaseModel):
    requests: List[GenerationRequest] = Field(..., max_items=8)
    priority: str = Field(default="normal")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    job_id: str
    status: str
    message: str
    estimated_time: Optional[int] = None


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    result_images: List[str]
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class TimelineAssetPayload(BaseModel):
    id: str
    name: str
    kind: Literal["video", "audio", "image"]
    duration: float = Field(ge=0.0)
    status: str
    url: Optional[str] = None
    download_url: Optional[str] = None
    waveform: Optional[List[float]] = None
    file_size: int = Field(default=0, ge=0)
    job_id: Optional[str] = None
    created_at: Optional[str] = None
    mime_type: Optional[str] = None


class TimelineClipPayload(BaseModel):
    id: str
    asset_id: str
    start: float = Field(ge=0.0)
    duration: float = Field(gt=0.0)
    layer: Literal["video", "audio"]


class ProxyPreviewPayload(BaseModel):
    status: Literal["idle", "processing", "ready", "error", "failed"]
    proxy_url: Optional[str] = None
    job_id: Optional[str] = None
    requested_at: Optional[str] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None


class VideoTimelinePayload(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default="", max_length=1000)
    frame_rate: int = Field(default=24, ge=1, le=120)
    total_duration: Optional[float] = Field(default=None, ge=0.0)
    assets: List[TimelineAssetPayload] = Field(default_factory=list)
    clips: List[TimelineClipPayload] = Field(default_factory=list)
    proxy_preview: Optional[ProxyPreviewPayload] = None


class VideoTimelineResponse(BaseModel):
    id: str
    name: str
    description: str
    frame_rate: int
    total_duration: float
    job_id: Optional[str]
    created_at: str
    updated_at: str
    assets: List[TimelineAssetPayload]
    clips: List[TimelineClipPayload]
    proxy_preview: Optional[ProxyPreviewPayload] = None


class VideoProxyPreviewResponse(BaseModel):
    job_id: Optional[str] = None
    status: Literal["idle", "processing", "ready", "failed", "error"]
    proxy_url: Optional[str] = None
    updated_at: Optional[str] = None
    message: Optional[str] = None


class VideoAssetWaveformResponse(BaseModel):
    asset_id: str
    waveform: List[float] = Field(default_factory=list)
    sample_rate: Optional[int] = None
    peak_amplitude: Optional[float] = None
    generated_at: Optional[str] = None
    status: Literal["processing", "ready", "failed"] = "ready"


def _compute_total_duration(clips: List[TimelineClipPayload]) -> float:
    if not clips:
        return 0.0
    return max((clip.start + clip.duration for clip in clips), default=0.0)


def _serialise_timeline(record) -> VideoTimelineResponse:
    payload = record.timeline_payload or {}
    assets_payload = payload.get("assets", [])
    clips_payload = payload.get("clips", [])

    def _safe_model(model_cls, data):
        if isinstance(data, dict):
            return model_cls(**data)
        raise ValueError("Invalid timeline payload")

    assets = []
    for asset in assets_payload:
        try:
            assets.append(_safe_model(TimelineAssetPayload, asset))
        except Exception:
            continue

    clips = []
    for clip in clips_payload:
        try:
            clips.append(_safe_model(TimelineClipPayload, clip))
        except Exception:
            continue

    proxy_preview_data = payload.get("proxy_preview")
    proxy_preview: Optional[ProxyPreviewPayload] = None
    if isinstance(proxy_preview_data, dict):
        try:
            proxy_preview = ProxyPreviewPayload(**proxy_preview_data)
        except Exception:
            proxy_preview = None

    created_at = record.created_at.isoformat() if record.created_at else datetime.utcnow().isoformat()
    updated_at = record.updated_at.isoformat() if record.updated_at else created_at

    return VideoTimelineResponse(
        id=record.id,
        name=record.name,
        description=record.description or "",
        frame_rate=record.frame_rate,
        total_duration=record.total_duration,
        job_id=record.job_id,
        created_at=created_at,
        updated_at=updated_at,
        assets=assets,
        clips=clips,
        proxy_preview=proxy_preview,
    )


@router.post("/single", response_model=GenerationResponse)
async def generate_single_image(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(verify_token),
):
    user_id = current_user.id
    job_id = str(uuid.uuid4())

    db = DatabaseService()
    try:
        job_metadata: Dict[str, Any] = {
            "scheduler": request.scheduler,
            "quality": request.quality,
            "style": request.style,
            "persona_id": request.persona_id,
        }
        job_metadata.update(request.metadata)

        if request.persona_id:
            persona = db.get_persona(request.persona_id, user_id)
            if persona:
                request.prompt = f"{persona.style_prompt}, {request.prompt}"
                if persona.negative_prompt:
                    request.negative_prompt = f"{persona.negative_prompt}, {request.negative_prompt}"
                if persona.lora_models:
                    request.lora_models.extend(persona.lora_models)
                job_metadata.update(
                    {
                        "persona_name": persona.name,
                        "persona_tags": persona.tags or [],
                        "persona_is_nsfw": persona.is_nsfw,
                    }
                )

        db.create_job(
            id=job_id,
            user_id=user_id,
            persona_id=request.persona_id,
            job_type=request.job_type,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            model_name=request.model_name,
            lora_models=request.lora_models,
            parameters={
                "width": request.width,
                "height": request.height,
                "num_inference_steps": request.num_inference_steps,
                "guidance_scale": request.guidance_scale,
                "num_images": request.num_images,
                "seed": request.seed,
                "model_name": request.model_name,
                "scheduler": request.scheduler,
                "quality": request.quality,
                "style": request.style,
            },
            status="pending",
            metadata=job_metadata,
            is_nsfw=request.is_nsfw,
        )

        request_payload = request.dict()
        priority_tag = "realtime"
        if USE_CELERY:
            background_tasks.add_task(
                submit_generation_job, job_id, request_payload, priority_tag
            )
        else:
            background_tasks.add_task(
                schedule_local_job, job_id, request_payload, priority_tag
            )

        estimated_time = request.num_images * 5
        return GenerationResponse(
            job_id=job_id,
            status="queued",
            message="Generation job queued successfully",
            estimated_time=estimated_time,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create generation job: {exc}")
    finally:
        db.close()


@router.post("/video", response_model=GenerationResponse)
async def generate_video(
    background_tasks: BackgroundTasks,
    prompt: str = Form(..., min_length=1, max_length=2000),
    duration_seconds: int = Form(6, ge=1, le=60),
    reference_image: Optional[str] = Form(None, max_length=2000),
    model_name: str = Form("sadtalker", min_length=1, max_length=100),
    metadata: Optional[str] = Form(None),
    persona_id: Optional[int] = Form(None),
    audio_file: UploadFile = File(...),
    current_user=Depends(verify_token),
):
    user_id = current_user.id
    job_id = str(uuid.uuid4())

    try:
        metadata_payload: Dict[str, Any] = {}
        if metadata:
            try:
                metadata_payload = json.loads(metadata)
                if not isinstance(metadata_payload, dict):
                    raise ValueError("metadata must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="Invalid metadata payload") from exc

        audio_directory: Path = settings.media_directory / "audio"
        audio_directory.mkdir(parents=True, exist_ok=True)

        original_name = audio_file.filename or "audio"
        _, extension = os.path.splitext(original_name)
        if not extension:
            extension = ".bin"
        stored_audio_path = audio_directory / f"{uuid.uuid4().hex}{extension}"

        contents = await audio_file.read()
        stored_audio_path.write_bytes(contents)

        audio_artifact = {
            "filename": original_name,
            "content_type": audio_file.content_type or "application/octet-stream",
            "encoding": "base64",
            "data": base64.b64encode(contents).decode("ascii"),
        }

        job_metadata: Dict[str, Any] = dict(metadata_payload)
        job_metadata["audio_path"] = str(stored_audio_path)

        parameters: Dict[str, Any] = {
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "model_name": model_name,
        }
        if reference_image:
            parameters["reference_image"] = reference_image
        parameters["audio_path"] = str(stored_audio_path)

        db = DatabaseService()
        try:
            db.create_job(
                id=job_id,
                user_id=user_id,
                persona_id=persona_id,
                job_type="video",
                prompt=prompt,
                negative_prompt="",
                model_name=model_name,
                lora_models=[],
                parameters=parameters,
                status="pending",
                metadata=job_metadata,
                is_nsfw=False,
            )
        finally:
            db.close()

        request_payload: Dict[str, Any] = {
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "model_name": model_name,
            "metadata": metadata_payload,
            "audio_path": str(stored_audio_path),
            "audio_artifact": audio_artifact,
        }
        if reference_image:
            request_payload["reference_image"] = reference_image
        if persona_id is not None:
            request_payload["persona_id"] = persona_id

        if USE_CELERY:
            background_tasks.add_task(generate_video_task.delay, job_id, request_payload)
            background_tasks.add_task(schedule_job_queued_notification, job_id)
        else:
            background_tasks.add_task(schedule_local_video_job, job_id, request_payload)

        estimated_time = max(duration_seconds, 1) * 5
        return GenerationResponse(
            job_id=job_id,
            status="queued",
            message="Video generation job queued successfully",
            estimated_time=estimated_time,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create video job: {exc}")


@router.post("/video/timeline", response_model=VideoTimelineResponse)
async def save_video_timeline(
    payload: VideoTimelinePayload,
    current_user=Depends(verify_token),
):
    timeline_id = payload.id or str(uuid.uuid4())
    total_duration = payload.total_duration
    if total_duration is None:
        total_duration = _compute_total_duration(payload.clips)

    timeline_data = {
        "assets": [asset.dict() for asset in payload.assets],
        "clips": [clip.dict() for clip in payload.clips],
    }
    if payload.proxy_preview:
        timeline_data["proxy_preview"] = payload.proxy_preview.dict()

    db = DatabaseService()
    try:
        existing = db.get_video_timeline(timeline_id, current_user.id) if payload.id else None
        description = payload.description or ""

        if existing is None:
            record = db.create_video_timeline(
                timeline_id=timeline_id,
                user_id=current_user.id,
                name=payload.name,
                description=description,
                frame_rate=payload.frame_rate,
                total_duration=total_duration,
                assets=timeline_data["assets"],
                clips=timeline_data["clips"],
            )
        else:
            record = db.update_video_timeline(
                timeline_id=timeline_id,
                user_id=current_user.id,
                name=payload.name,
                description=description,
                frame_rate=payload.frame_rate,
                total_duration=total_duration,
                timeline=timeline_data,
            )
            if record is None:
                raise HTTPException(status_code=404, detail="Timeline not found")

        return _serialise_timeline(record)
    finally:
        db.close()


@router.get("/video/timeline/{timeline_id}", response_model=VideoTimelineResponse)
async def get_video_timeline(timeline_id: str, current_user=Depends(verify_token)):
    db = DatabaseService()
    try:
        record = db.get_video_timeline(timeline_id, current_user.id)
        if record is None:
            raise HTTPException(status_code=404, detail="Timeline not found")
        return _serialise_timeline(record)
    finally:
        db.close()


@router.post("/video/timeline/{timeline_id}/render", response_model=GenerationResponse)
async def queue_video_timeline_render(
    timeline_id: str,
    current_user=Depends(verify_token),
):
    db = DatabaseService()
    try:
        timeline = db.get_video_timeline(timeline_id, current_user.id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="Timeline not found")

        if timeline.job_id:
            job = db.get_job(timeline.job_id)
            if job and job.status not in {"failed", "completed"}:
                raise HTTPException(status_code=409, detail="Timeline already queued")

        job_id = str(uuid.uuid4())
        timeline_payload = timeline.timeline_payload or {}
        db.create_job(
            id=job_id,
            user_id=current_user.id,
            persona_id=None,
            job_type="video_timeline",
            prompt=timeline.name,
            negative_prompt="",
            model_name="timeline-compositor",
            lora_models=[],
            parameters={
                "timeline_id": timeline.id,
                "frame_rate": timeline.frame_rate,
                "total_duration": timeline.total_duration,
            },
            status="queued",
            metadata={"timeline_assets": timeline_payload.get("assets", [])},
            is_nsfw=False,
        )
        db.update_video_timeline(timeline_id, current_user.id, job_id=job_id)

        estimated_time = max(int(round(timeline.total_duration or 1)), 1) * 4
        return GenerationResponse(
            job_id=job_id,
            status="queued",
            message="Timeline render job queued successfully",
            estimated_time=estimated_time,
        )
    finally:
        db.close()


def _resolve_proxy_status(status: Optional[str]) -> str:
    value = (status or "").lower()
    if value in {"ready", "completed", "done", "success"}:
        return "ready"
    if value in {"processing", "running", "queued", "pending"}:
        return "processing"
    if value in {"failed", "error"}:
        return "failed"
    return "idle"


def _proxy_media_url(timeline_id: str) -> str:
    return f"/media/video_proxies/{timeline_id}.webm"


@router.post("/video/timeline/{timeline_id}/proxy", response_model=VideoProxyPreviewResponse)
async def queue_video_timeline_proxy(
    timeline_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    current_user=Depends(verify_token),
):
    db = DatabaseService()
    try:
        timeline = db.get_video_timeline(timeline_id, current_user.id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="Timeline not found")

        timeline_payload = timeline.timeline_payload or {}
        preview_state = dict(timeline_payload.get("proxy_preview") or {})
        proxy_path = settings.media_directory / "video_proxies" / f"{timeline_id}.webm"

        normalized_status = _resolve_proxy_status(preview_state.get("status"))
        if normalized_status in {"processing"} and not force:
            return VideoProxyPreviewResponse(
                job_id=preview_state.get("job_id"),
                status="processing",
                proxy_url=preview_state.get("proxy_url"),
                updated_at=preview_state.get("updated_at"),
                message=preview_state.get("message") or "Proxy en cours de génération",
            )

        if (
            normalized_status == "ready"
            and proxy_path.exists()
            and not force
        ):
            proxy_url = preview_state.get("proxy_url") or _proxy_media_url(timeline_id)
            return VideoProxyPreviewResponse(
                job_id=preview_state.get("job_id"),
                status="ready",
                proxy_url=proxy_url,
                updated_at=preview_state.get("updated_at"),
                message=preview_state.get("message"),
            )

        job_id = str(uuid.uuid4())
        requested_at = datetime.utcnow().isoformat()

        db.create_job(
            id=job_id,
            user_id=current_user.id,
            persona_id=None,
            job_type="video_proxy",
            prompt=f"Proxy preview for {timeline.name}",
            negative_prompt="",
            model_name="timeline-proxy",
            lora_models=[],
            parameters={"timeline_id": timeline_id},
            status="queued",
            metadata={"timeline_assets": timeline_payload.get("assets", [])},
            is_nsfw=False,
        )

        preview_state.update(
            {
                "status": "processing",
                "job_id": job_id,
                "requested_at": requested_at,
                "updated_at": requested_at,
                "message": "Proxy en cours de génération",
            }
        )
        timeline_payload["proxy_preview"] = preview_state
        db.update_video_timeline(
            timeline_id,
            current_user.id,
            timeline=timeline_payload,
        )

        if USE_CELERY:
            background_tasks.add_task(
                generate_timeline_proxy_task.delay,
                job_id,
                timeline_id,
                current_user.id,
                force,
            )
            background_tasks.add_task(schedule_job_queued_notification, job_id)
        else:
            background_tasks.add_task(
                schedule_local_timeline_proxy,
                job_id,
                timeline_id,
                current_user.id,
                force,
            )

        return VideoProxyPreviewResponse(
            job_id=job_id,
            status="processing",
            proxy_url=preview_state.get("proxy_url"),
            updated_at=requested_at,
            message=preview_state.get("message"),
        )
    finally:
        db.close()


@router.get("/video/timeline/{timeline_id}/proxy", response_model=VideoProxyPreviewResponse)
async def get_video_timeline_proxy(
    timeline_id: str,
    current_user=Depends(verify_token),
):
    db = DatabaseService()
    try:
        timeline = db.get_video_timeline(timeline_id, current_user.id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="Timeline not found")

        timeline_payload = timeline.timeline_payload or {}
        preview_state = dict(timeline_payload.get("proxy_preview") or {})
        proxy_path = settings.media_directory / "video_proxies" / f"{timeline_id}.webm"

        proxy_url = preview_state.get("proxy_url")
        if proxy_path.exists():
            proxy_url = proxy_url or _proxy_media_url(timeline_id)
            if _resolve_proxy_status(preview_state.get("status")) != "ready":
                preview_state.update(
                    {
                        "status": "ready",
                        "proxy_url": proxy_url,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                )
                timeline_payload["proxy_preview"] = preview_state
                db.update_video_timeline(
                    timeline_id,
                    current_user.id,
                    timeline=timeline_payload,
                )

        status = _resolve_proxy_status(preview_state.get("status"))
        if proxy_path.exists() and status != "failed":
            status = "ready"

        return VideoProxyPreviewResponse(
            job_id=preview_state.get("job_id"),
            status=status if status != "idle" else ("ready" if proxy_path.exists() else "idle"),
            proxy_url=proxy_url,
            updated_at=preview_state.get("updated_at"),
            message=preview_state.get("message"),
        )
    finally:
        db.close()

@router.post("/batch", response_model=GenerationResponse)
async def generate_batch_images(
    request: BatchGenerationRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(verify_token),
):
    user_id = current_user.id
    if len(request.requests) > 8:
        raise HTTPException(status_code=400, detail="Maximum 8 images per batch")

    batch_job_id = str(uuid.uuid4())
    db = DatabaseService()
    try:
        job_ids = []
        total_images = 0

        batch_metadata = {"priority": request.priority}
        batch_metadata.update(request.metadata)

        for index, gen_request in enumerate(request.requests):
            job_id = f"{batch_job_id}_{index}"
            job_ids.append(job_id)
            total_images += gen_request.num_images

            persona = None
            if gen_request.persona_id:
                persona = db.get_persona(gen_request.persona_id, user_id)
                if persona:
                    gen_request.prompt = f"{persona.style_prompt}, {gen_request.prompt}"
                    if persona.negative_prompt:
                        gen_request.negative_prompt = f"{persona.negative_prompt}, {gen_request.negative_prompt}"
                    if persona.lora_models:
                        gen_request.lora_models.extend(persona.lora_models)

            job_metadata: Dict[str, Any] = {
                "batch_id": batch_job_id,
                "batch_priority": request.priority,
                "scheduler": gen_request.scheduler,
                "quality": gen_request.quality,
                "style": gen_request.style,
                "persona_id": gen_request.persona_id,
            }

            if persona:
                job_metadata.update(
                    {
                        "persona_name": persona.name,
                        "persona_tags": persona.tags or [],
                        "persona_is_nsfw": persona.is_nsfw,
                    }
                )

            job_metadata.update(gen_request.metadata)
            job_metadata.update(batch_metadata)

            db.create_job(
                id=job_id,
                user_id=user_id,
                persona_id=gen_request.persona_id,
                job_type=gen_request.job_type,
                prompt=gen_request.prompt,
                negative_prompt=gen_request.negative_prompt,
                model_name=gen_request.model_name,
                lora_models=gen_request.lora_models,
                parameters={
                    "width": gen_request.width,
                    "height": gen_request.height,
                    "num_inference_steps": gen_request.num_inference_steps,
                    "guidance_scale": gen_request.guidance_scale,
                    "num_images": gen_request.num_images,
                    "seed": gen_request.seed,
                    "batch_id": batch_job_id,
                    "priority": request.priority,
                    "model_name": gen_request.model_name,
                    "scheduler": gen_request.scheduler,
                    "quality": gen_request.quality,
                    "style": gen_request.style,
                },
                status="pending",
                metadata=job_metadata,
                is_nsfw=gen_request.is_nsfw,
            )

        requests_payload = [req.dict() for req in request.requests]
        batch_priority_tag = _resolve_batch_priority(request.priority)

        if USE_CELERY:
            background_tasks.add_task(
                submit_batch_generation_job,
                job_ids,
                requests_payload,
                batch_priority_tag,
            )
        else:
            background_tasks.add_task(
                schedule_local_batch,
                job_ids,
                requests_payload,
                batch_priority_tag,
            )

        estimated_time = total_images * 5
        return GenerationResponse(
            job_id=batch_job_id,
            status="queued",
            message=f"Batch generation job queued ({len(request.requests)} requests)",
            estimated_time=estimated_time,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create batch job: {exc}")
    finally:
        db.close()


@router.get("/status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str, current_user=Depends(verify_token)):
    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        if not job or job.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobStatus(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            result_images=job.result_images or [],
            error_message=job.error_message,
            created_at=job.created_at.isoformat(),
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
        )
    finally:
        db.close()


@router.delete("/cancel/{job_id}")
async def cancel_job(job_id: str, current_user=Depends(verify_token)):
    user_id = current_user.id
    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if job.status in ["completed", "failed", "cancelled"]:
            raise HTTPException(status_code=400, detail="Job already finalised")

        db.update_job(job_id, status="cancelled", progress=0.0)
        return {"message": "Job cancelled successfully"}
    finally:
        db.close()


@router.get("/history")
async def get_generation_history(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    current_user=Depends(verify_token),
):
    user_id = current_user.id
    db = DatabaseService()
    try:
        jobs, total = db.get_user_jobs(
            user_id,
            limit=limit,
            offset=offset,
            status=status,
        )

        return {
            "jobs": [
                {
                    "job_id": job.id,
                    "status": job.status,
                    "progress": job.progress,
                    "prompt": job.prompt[:100] + "..." if len(job.prompt) > 100 else job.prompt,
                    "result_images": job.result_images or [],
                    "created_at": job.created_at.isoformat(),
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                }
                for job in jobs
            ],
            "total": total,
        }
    finally:
        db.close()


async def _run_local_job(job_id: str, request_data: dict, priority_tag: str):
    await _generation_service.notify_job_queued(job_id)
    await _generation_service.enqueue_job(job_id, request_data, priority_tag=priority_tag)


def schedule_local_job(job_id: str, request_data: dict, priority_tag: str):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local_job(job_id, request_data, priority_tag))
    else:
        loop.create_task(_run_local_job(job_id, request_data, priority_tag))


async def _run_local_batch(
    job_ids: List[str], requests_data: List[dict], priority_tag: str
):
    await _generation_service.notify_batch_queued(job_ids)
    for job_id, request in zip(job_ids, requests_data):
        await _generation_service.enqueue_job(job_id, request, priority_tag=priority_tag)


async def _run_local_video_job(
    job_id: str, request_data: dict, priority_tag: str | None = None
):
    await _generation_service.notify_job_queued(job_id)
    await _generation_service.process_video_job(job_id, request_data)


def schedule_local_batch(job_ids: List[str], requests_data: List[dict], priority_tag: str):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local_batch(job_ids, requests_data, priority_tag))
    else:
        loop.create_task(_run_local_batch(job_ids, requests_data, priority_tag))


def schedule_local_video_job(job_id: str, request_data: dict, priority_tag: str | None = None):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local_video_job(job_id, request_data, priority_tag))
    else:
        loop.create_task(_run_local_video_job(job_id, request_data, priority_tag))


async def _run_local_timeline_proxy(
    job_id: str,
    timeline_id: str,
    user_id: int,
    force: bool = False,
):
    await _generation_service.generate_timeline_proxy(
        job_id,
        timeline_id,
        user_id,
        force=force,
    )


def schedule_local_timeline_proxy(
    job_id: str, timeline_id: str, user_id: int, force: bool = False
):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local_timeline_proxy(job_id, timeline_id, user_id, force))
    else:
        loop.create_task(
            _run_local_timeline_proxy(job_id, timeline_id, user_id, force)
        )


async def _run_local_waveform(asset_id: str, sample_points: int = 128, force: bool = False):
    await _generation_service.generate_asset_waveform(
        asset_id,
        sample_points=sample_points,
        force=force,
    )


def schedule_local_waveform(asset_id: str, sample_points: int = 128, force: bool = False):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local_waveform(asset_id, sample_points, force))
    else:
        loop.create_task(
            _run_local_waveform(asset_id, sample_points, force)
        )


def schedule_job_queued_notification(job_id: str):
    async def _notify():
        await _generation_service.notify_job_queued(job_id)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_notify())
    else:
        loop.create_task(_notify())


def set_generation_service(service):  # used from main to inject shared instance
    global _generation_service
    _generation_service = service
