"""
SEIDRA Personas API
Advanced AI-driven persona management system
"""

import asyncio
import time
from datetime import datetime
import sys
from importlib import import_module
from typing import Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from api.auth import verify_token
from services.generation_service import get_generation_service

if TYPE_CHECKING:  # pragma: no cover
    from services.database import DatabaseService as _DatabaseService

router = APIRouter()


def _get_database_service():
    alias = sys.modules.get("seidra._active_database_module")
    if alias is None:
        alias = import_module("services.database")

    return alias.DatabaseService  # type: ignore[attr-defined]

# Request/Response models
class PersonaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    style_prompt: str = Field(..., min_length=1, max_length=1000)
    negative_prompt: str = Field(default="", max_length=1000)
    lora_models: List[str] = Field(default_factory=list)
    generation_params: dict = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    is_favorite: bool = Field(default=False)
    is_nsfw: bool = Field(default=False)
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class PersonaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    style_prompt: Optional[str] = Field(None, min_length=1, max_length=1000)
    negative_prompt: Optional[str] = Field(None, max_length=1000)
    lora_models: Optional[List[str]] = None
    generation_params: Optional[dict] = None
    tags: Optional[List[str]] = None
    is_favorite: Optional[bool] = None
    is_nsfw: Optional[bool] = None
    avatar_url: Optional[str] = Field(default=None, max_length=500)


class PersonaResponse(BaseModel):
    id: int
    name: str
    description: str
    style_prompt: str
    negative_prompt: str
    lora_models: List[str]
    generation_params: dict
    tags: List[str]
    is_favorite: bool
    is_nsfw: bool
    avatar_url: Optional[str]
    created_at: str
    updated_at: str


class PersonaPreviewResponse(BaseModel):
    job_id: str
    status: str
    message: str
    persona_id: int
    estimated_time: int


def _serialize_persona(persona) -> PersonaResponse:
    return PersonaResponse(
        id=persona.id,
        name=persona.name,
        description=persona.description or "",
        style_prompt=persona.style_prompt,
        negative_prompt=persona.negative_prompt or "",
        lora_models=persona.lora_models or [],
        generation_params=persona.generation_params or {},
        tags=persona.tags or [],
        is_favorite=bool(persona.is_favorite),
        is_nsfw=bool(persona.is_nsfw),
        avatar_url=persona.avatar_url,
        created_at=persona.created_at.isoformat(),
        updated_at=persona.updated_at.isoformat(),
    )


def _simulate_preview_job(job_id: str, preview_payload: Dict[str, str]) -> None:
    """Simulate a lightweight preview generation job lifecycle."""

    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        db.update_job(job_id, status="processing", progress=0.25)
        time.sleep(0.1)
        db.update_job(
            job_id,
            status="completed",
            progress=1.0,
            result_images=[preview_payload["preview_image"]],
            metadata={**preview_payload.get("metadata", {}), "preview": True},
            completed_at=datetime.utcnow(),
        )
    finally:
        db.close()


def _dispatch_preview_notification(job_id: str) -> None:
    try:
        generation_service = get_generation_service()
    except Exception:
        # In local/test environments the generation stack might not be initialised.
        # Failing silently keeps the preview job queue stable for API clients.
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        loop.create_task(generation_service.notify_job_queued(job_id))
    else:
        asyncio.run(generation_service.notify_job_queued(job_id))

@router.get("/", response_model=List[PersonaResponse])
async def list_personas(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, min_length=1, max_length=100),
    is_favorite: Optional[bool] = Query(None),
    include_nsfw: bool = Query(False),
    current_user=Depends(verify_token),
):
    """List personas with filtering and pagination support."""

    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        personas, total = db.get_personas(
            user_id,
            limit=limit,
            offset=offset,
            search=search,
            is_favorite=is_favorite,
            include_nsfw=include_nsfw,
            return_total=True,
        )
        response.headers["X-Total-Count"] = str(total)
        return [_serialize_persona(persona) for persona in personas]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list personas: {str(e)}")
    finally:
        db.close()

@router.post("/", response_model=PersonaResponse)
async def create_persona(persona_data: PersonaCreate, current_user=Depends(verify_token)):
    """Create new persona"""
    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        persona = db.create_persona(
            user_id=user_id,
            name=persona_data.name,
            description=persona_data.description,
            style_prompt=persona_data.style_prompt,
            negative_prompt=persona_data.negative_prompt,
            lora_models=persona_data.lora_models,
            generation_params=persona_data.generation_params,
            tags=persona_data.tags,
            is_favorite=persona_data.is_favorite,
            is_nsfw=persona_data.is_nsfw,
            avatar_url=persona_data.avatar_url,
        )

        return _serialize_persona(persona)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create persona: {str(e)}")
    finally:
        db.close()

@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(persona_id: int, current_user=Depends(verify_token)):
    """Get specific persona"""
    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        persona = db.get_persona(persona_id, user_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        
        return _serialize_persona(persona)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get persona: {str(e)}")
    finally:
        db.close()

@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: int,
    persona_data: PersonaUpdate,
    current_user=Depends(verify_token),
):
    """Update existing persona"""
    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        # Get current persona
        persona = db.get_persona(persona_id, user_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        
        # Update with provided data
        update_data = {}
        for field, value in persona_data.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")
        
        updated_persona = db.update_persona(persona_id, user_id, **update_data)
        if not updated_persona:
            raise HTTPException(status_code=500, detail="Failed to update persona")
        
        return _serialize_persona(updated_persona)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update persona: {str(e)}")
    finally:
        db.close()

@router.delete("/{persona_id}")
async def delete_persona(persona_id: int, current_user=Depends(verify_token)):
    """Delete persona"""
    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        success = db.delete_persona(persona_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Persona not found")
        
        return {"message": "Persona deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete persona: {str(e)}")
    finally:
        db.close()

@router.post("/{persona_id}/duplicate")
async def duplicate_persona(
    persona_id: int,
    new_name: str,
    current_user=Depends(verify_token),
):
    """Duplicate existing persona with new name"""
    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        # Get original persona
        original = db.get_persona(persona_id, user_id)
        if not original:
            raise HTTPException(status_code=404, detail="Persona not found")
        
        # Create duplicate
        duplicate = db.create_persona(
            user_id=user_id,
            name=new_name,
            description=f"Copy of {original.name}",
            style_prompt=original.style_prompt,
            negative_prompt=original.negative_prompt or "",
            lora_models=original.lora_models or [],
            generation_params=original.generation_params or {},
            tags=original.tags or [],
            is_favorite=bool(original.is_favorite),
            is_nsfw=bool(original.is_nsfw),
            avatar_url=original.avatar_url,
        )

        return _serialize_persona(duplicate)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to duplicate persona: {str(e)}")
    finally:
        db.close()

@router.post("/{persona_id}/preview", response_model=PersonaPreviewResponse)
async def preview_persona_style(
    persona_id: int,
    background_tasks: BackgroundTasks,
    current_user=Depends(verify_token),
):
    """Queue a lightweight preview generation job for a persona."""

    user_id = current_user.id
    DatabaseService = _get_database_service()
    db = DatabaseService()
    try:
        persona = db.get_persona(persona_id, user_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

        job_id = str(uuid4())
        persona_params = persona.generation_params or {}
        width = int(persona_params.get("width", 768))
        height = int(persona_params.get("height", 768))
        inference_steps = int(persona_params.get("num_inference_steps", 25))
        guidance_scale = float(persona_params.get("guidance_scale", 7.5))
        scheduler = persona_params.get("scheduler", "ddim")
        model_name = persona_params.get("model_name", "sdxl-base")
        quality = persona_params.get("quality", "standard")

        preview_image = f"/media/persona_previews/{persona_id}_{job_id}.png"
        preview_metadata: Dict[str, str] = {
            "persona_id": str(persona_id),
            "persona_name": persona.name,
        }

        db.create_job(
            id=job_id,
            user_id=user_id,
            persona_id=persona_id,
            job_type="persona_preview",
            prompt=persona.style_prompt,
            negative_prompt=persona.negative_prompt or "",
            model_name=model_name,
            lora_models=persona.lora_models or [],
            parameters={
                "width": width,
                "height": height,
                "num_inference_steps": inference_steps,
                "guidance_scale": guidance_scale,
                "scheduler": scheduler,
                "quality": quality,
                "preview": True,
            },
            status="queued",
            metadata={
                "preview": True,
                "persona_name": persona.name,
                "persona_tags": persona.tags or [],
                "persona_is_nsfw": persona.is_nsfw,
            },
            is_nsfw=bool(persona.is_nsfw),
        )

        preview_payload = {
            "preview_image": preview_image,
            "metadata": preview_metadata,
        }
        background_tasks.add_task(_simulate_preview_job, job_id, preview_payload)

        background_tasks.add_task(_dispatch_preview_notification, job_id)

        estimated_time = 3
        return PersonaPreviewResponse(
            job_id=job_id,
            status="queued",
            message="Preview generation queued",
            persona_id=persona_id,
            estimated_time=estimated_time,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")
    finally:
        db.close()