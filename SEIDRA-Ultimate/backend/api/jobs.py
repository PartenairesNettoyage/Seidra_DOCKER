"""Job management endpoints for the SEIDRA Ultimate backend."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sys
from importlib import import_module
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from api.auth import verify_token
from services.generation_service import get_generation_service
from api.generation import USE_CELERY, schedule_local_job
from workers.generation_worker import submit_generation_job


if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from services.database import DatabaseService as _DatabaseService
    from services.database import GenerationJob


def _get_database_module():
    alias = sys.modules.get("seidra._active_database_module")
    if alias is not None:
        return alias

    return import_module("services.database")


def _get_database_service():
    return _get_database_module().DatabaseService  # type: ignore[attr-defined]


router = APIRouter()
_generation_service = get_generation_service()


class JobParameters(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    num_inference_steps: Optional[int] = None
    guidance_scale: Optional[float] = None
    num_images: Optional[int] = None
    seed: Optional[int] = None
    scheduler: Optional[str] = None
    quality: Optional[str] = None
    style: Optional[str] = None
    model_name: Optional[str] = None


class JobSummary(BaseModel):
    job_id: str
    status: str
    prompt: str
    progress: float
    job_type: str
    model_name: str
    persona_id: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]
    completed_at: Optional[datetime]


class JobListResponse(BaseModel):
    total: int
    jobs: List[JobSummary]


class JobDetail(JobSummary):
    negative_prompt: str
    parameters: Dict[str, Any]
    result_images: List[str]
    metadata: Dict[str, Any]
    error_message: Optional[str]


class JobStats(BaseModel):
    total: int
    by_status: Dict[str, int]
    average_duration: Optional[float]
    last_completed: Optional[str]


class RetryResponse(BaseModel):
    job_id: str
    new_job_id: str
    status: str
    message: str


def _map_job(job: "GenerationJob") -> JobSummary:
    return JobSummary(
        job_id=job.id,
        status=job.status,
        prompt=job.prompt,
        progress=job.progress,
        job_type=job.job_type,
        model_name=job.model_name,
        persona_id=job.persona_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


@router.get("/", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    persona_id: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None),
    current_user=Depends(verify_token),
):
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        user_id = current_user.id
        jobs, total = db.get_user_jobs(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status=status,
            job_type=job_type,
            persona_id=persona_id,
            search=search,
        )
        return JobListResponse(total=total, jobs=[_map_job(job) for job in jobs])
    finally:
        db.close()


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, current_user=Depends(verify_token)):
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        if not job or (
            job.user_id != current_user.id
            and not getattr(current_user, "is_system", False)
        ):
            raise HTTPException(status_code=404, detail="Job not found")

        return JobDetail(
            **_map_job(job).dict(),
            negative_prompt=job.negative_prompt,
            parameters=job.parameters or {},
            result_images=job.result_images or [],
            metadata=job.metadata_payload or {},
            error_message=job.error_message,
        )
    finally:
        db.close()


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, current_user=Depends(verify_token)):
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        if not job or (
            job.user_id != current_user.id
            and not getattr(current_user, "is_system", False)
        ):
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status in {"completed", "failed", "cancelled"}:
            raise HTTPException(status_code=400, detail="Job already finalized")

        db.update_job(
            job_id,
            status="cancelled",
            progress=0.0,
            completed_at=datetime.utcnow(),
        )
        await _generation_service.websocket_manager.dispatch_event(
            {"type": "job_cancelled", "job_id": job_id},
            channels={"jobs"},
            user_id=job.user_id,
        )
        return {"message": "Job cancelled", "job_id": job_id}
    finally:
        db.close()


@router.post("/{job_id}/retry", response_model=RetryResponse)
async def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(verify_token),
):
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        job = db.get_job(job_id)
        if not job or (
            job.user_id != current_user.id
            and not getattr(current_user, "is_system", False)
        ):
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status not in {"failed", "cancelled", "completed"}:
            raise HTTPException(status_code=400, detail="Job is still running")

        new_job_id = str(uuid.uuid4())
        request_payload = {
            "prompt": job.prompt,
            "negative_prompt": job.negative_prompt,
            "persona_id": job.persona_id,
            "lora_models": job.lora_models or [],
            "lora_weights": job.metadata_payload.get("lora_weights") if job.metadata_payload else None,
            "model_name": job.model_name,
            "job_type": job.job_type,
            "metadata": job.metadata_payload or {},
            "is_nsfw": job.is_nsfw,
        }

        parameters = job.parameters or {}
        for key in [
            "width",
            "height",
            "num_inference_steps",
            "guidance_scale",
            "num_images",
            "seed",
            "scheduler",
            "quality",
            "style",
        ]:
            value = parameters.get(key)
            if value is not None:
                request_payload[key] = value

        request_payload.setdefault("num_inference_steps", 30)
        request_payload.setdefault("guidance_scale", 7.5)
        request_payload.setdefault("num_images", 1)
        request_payload.setdefault("scheduler", "ddim")
        request_payload.setdefault("quality", "high")

        db.create_job(
            id=new_job_id,
            user_id=job.user_id,
            persona_id=job.persona_id,
            job_type=job.job_type,
            prompt=job.prompt,
            negative_prompt=job.negative_prompt,
            model_name=job.model_name,
            lora_models=job.lora_models or [],
            parameters=job.parameters or {},
            status="pending",
            metadata=job.metadata_payload or {},
            is_nsfw=job.is_nsfw,
        )

        priority_tag = "realtime"
        if USE_CELERY:
            background_tasks.add_task(
                submit_generation_job, new_job_id, request_payload, priority_tag
            )
        else:
            background_tasks.add_task(
                schedule_local_job, new_job_id, request_payload, priority_tag
            )

        return RetryResponse(
            job_id=job_id,
            new_job_id=new_job_id,
            status="queued",
            message="Job re-queued successfully",
        )
    finally:
        db.close()


@router.get("/stats", response_model=JobStats)
async def get_job_stats(current_user=Depends(verify_token)):
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        stats = db.get_job_statistics(current_user.id)
        return JobStats(**stats)
    finally:
        db.close()
