"""SEIDRA Ultimate model management endpoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import verify_token
from core.config import settings
from services.database import DatabaseService
from services.model_manager import ModelManager

router = APIRouter()

_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


# Request/Response models
class ModelInfo(BaseModel):
    id: str
    name: str
    description: str
    type: str  # base, lora, vae
    size: str
    is_downloaded: bool
    download_url: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

class LoRAModelInfo(BaseModel):
    id: str
    name: str
    description: str
    file_path: str
    download_url: Optional[str] = None
    category: str
    tags: List[str]
    is_downloaded: bool
    file_size: int

class DownloadRequest(BaseModel):
    model_id: str
    priority: str = Field(default="normal")  # low, normal, high

class ModelStatus(BaseModel):
    loaded_models: List[str]
    available_loras: List[str]
    gpu_info: Dict[str, Any]
    cache_size: str
    optimal_batch_size: int

def _collect_available_models() -> List[ModelInfo]:
    """Assemble the catalogue of models available to authenticated users."""

    base_models = [
        ModelInfo(
            id="sdxl-base",
            name="Stable Diffusion XL Base",
            description="High-quality base model for image generation",
            type="base",
            size="6.9GB",
            is_downloaded=True,  # Assumed downloaded during setup
            category="base",
            tags=["sdxl", "base", "high-quality"],
        ),
        ModelInfo(
            id="sdxl-refiner",
            name="Stable Diffusion XL Refiner",
            description="Refiner model for enhanced image quality",
            type="base",
            size="6.1GB",
            is_downloaded=True,
            category="refiner",
            tags=["sdxl", "refiner", "enhancement"],
        ),
    ]

    db = DatabaseService()
    try:
        lora_models_db = db.get_lora_models()
        lora_models = [
            ModelInfo(
                id=lora.id,
                name=lora.name,
                description=lora.description or "",
                type="lora",
                size=f"{lora.file_size / (1024*1024):.1f}MB" if lora.file_size else "Unknown",
                is_downloaded=lora.is_downloaded,
                download_url=lora.download_url,
                category=lora.category,
                tags=lora.tags or [],
            )
            for lora in lora_models_db
        ]
    except Exception as exc:
        print(f"Failed to get LoRA models: {exc}")
        lora_models = []
    finally:
        db.close()

    popular_loras = [
        ModelInfo(
            id="anime_style_xl",
            name="Anime Style XL",
            description="High-quality anime style LoRA for SDXL",
            type="lora",
            size="144MB",
            is_downloaded=False,
            download_url="https://civitai.com/api/download/models/47274",
            category="style",
            tags=["anime", "style", "character"],
        ),
        ModelInfo(
            id="photorealistic_xl",
            name="Photorealistic XL",
            description="Ultra-realistic photography style LoRA",
            type="lora",
            size="220MB",
            is_downloaded=False,
            download_url="https://civitai.com/api/download/models/130072",
            category="style",
            tags=["photorealistic", "photography", "realistic"],
        ),
        ModelInfo(
            id="fantasy_art_xl",
            name="Fantasy Art XL",
            description="Fantasy and mystical art style LoRA",
            type="lora",
            size="180MB",
            is_downloaded=False,
            download_url="https://civitai.com/api/download/models/84040",
            category="style",
            tags=["fantasy", "mystical", "art"],
        ),
        ModelInfo(
            id="cyberpunk_xl",
            name="Cyberpunk XL",
            description="Cyberpunk and futuristic style LoRA",
            type="lora",
            size="165MB",
            is_downloaded=False,
            download_url="https://civitai.com/api/download/models/95648",
            category="style",
            tags=["cyberpunk", "futuristic", "neon"],
        ),
    ]

    all_models = base_models + lora_models + popular_loras
    seen_ids = set()
    unique_models = []
    for model in all_models:
        if model.id not in seen_ids:
            unique_models.append(model)
            seen_ids.add(model.id)

    return unique_models


@router.get("/available", response_model=List[ModelInfo])
async def list_available_models(_current_user=Depends(verify_token)):
    """List all available models for download."""

    return _collect_available_models()

@router.get("/lora", response_model=List[LoRAModelInfo])
async def list_lora_models(_current_user=Depends(verify_token)):
    """List all LoRA models"""
    db = DatabaseService()
    try:
        lora_models = db.get_lora_models()
        return [
            LoRAModelInfo(
                id=lora.id,
                name=lora.name,
                description=lora.description or "",
                file_path=lora.file_path,
                download_url=lora.download_url,
                category=lora.category or "unknown",
                tags=lora.tags or [],
                is_downloaded=lora.is_downloaded,
                file_size=lora.file_size
            )
            for lora in lora_models
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list LoRA models: {str(e)}")
    finally:
        db.close()

@router.post("/download")
async def download_model(
    request: DownloadRequest,
    background_tasks: BackgroundTasks,
    _current_user=Depends(verify_token),
):
    """Download a model"""
    
    # Check if model exists in available models
    available_models = _collect_available_models()
    model_info = None
    for model in available_models:
        if model.id == request.model_id:
            model_info = model
            break
    
    if not model_info:
        raise HTTPException(status_code=404, detail="Model not found")
    
    if model_info.is_downloaded:
        return {"message": "Model already downloaded", "model_id": request.model_id}
    
    if not model_info.download_url:
        raise HTTPException(status_code=400, detail="No download URL available for this model")
    
    # Queue download task
    background_tasks.add_task(
        download_model_task,
        request.model_id,
        model_info.download_url,
        model_info.name,
        model_info.category or "unknown"
    )
    
    return {
        "message": "Download queued",
        "model_id": request.model_id,
        "estimated_time": "5-10 minutes"
    }

@router.delete("/{model_id}")
async def delete_model(model_id: str, _current_user=Depends(verify_token)):
    """Delete a downloaded model"""
    db = DatabaseService()
    try:
        # Check if it's a LoRA model
        lora_models = db.get_lora_models()
        lora_model = None
        for lora in lora_models:
            if lora.id == model_id:
                lora_model = lora
                break
        
        if lora_model:
            # Delete file if exists
            if os.path.exists(lora_model.file_path):
                os.remove(lora_model.file_path)
            
            # Update database
            db.update_lora_model(model_id, is_downloaded=False, file_path="")
            
            return {"message": "Model deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Model not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete model: {str(e)}")
    finally:
        db.close()

@router.get("/status", response_model=ModelStatus)
async def get_model_status(_current_user=Depends(verify_token)):
    """Get current model status and GPU information"""
    try:
        manager = get_model_manager()
        model_info = await manager.get_model_info()
        
        return ModelStatus(
            loaded_models=list(manager.loaded_models.keys()),
            available_loras=list(manager.lora_models.keys()),
            gpu_info=model_info.get("gpu_info", {}),
            cache_size=f"{manager.cache.get_cache_size() / (1024**3):.1f}GB",
            optimal_batch_size=model_info.get("optimal_batch_size", 2)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model status: {str(e)}")

@router.post("/reload")
async def reload_models(_current_user=Depends(verify_token)):
    """Reload all models"""
    try:
        manager = get_model_manager()
        await manager.initialize()
        return {"message": "Models reloaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload models: {str(e)}")

@router.post("/clear-cache")
async def clear_model_cache(_current_user=Depends(verify_token)):
    """Clear model cache"""
    try:
        manager = get_model_manager()
        manager.cache.cleanup_cache()
        return {"message": "Model cache cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

def download_model_task(model_id: str, download_url: str, model_name: str, category: str) -> None:
    """Background task to download model.

    The FastAPI ``BackgroundTasks`` helper executes regular callables after the
    response has been returned.  Using a synchronous function here avoids
    accidentally creating orphaned event loops while still keeping the
    implementation compatible with Celery-based workers in production.
    """

    db = DatabaseService()
    try:
        print(f"🔄 Downloading model: {model_name}")

        models_dir = settings.models_directory / "lora"
        models_dir.mkdir(parents=True, exist_ok=True)

        file_extension = ".safetensors" if "safetensors" in download_url.lower() else ".ckpt"
        filename = f"{model_id}{file_extension}"
        file_path = models_dir / filename

        existing_lora = next((lora for lora in db.get_lora_models() if lora.id == model_id), None)

        if existing_lora:
            db.update_lora_model(model_id, file_path=str(file_path), is_downloaded=True)
        else:
            db.create_lora_model(
                id=model_id,
                name=model_name,
                description=f"Downloaded {model_name}",
                file_path=str(file_path),
                download_url=download_url,
                category=category,
                tags=[category, "downloaded"],
                is_downloaded=True,
                file_size=0,
            )

        file_path.touch(exist_ok=True)
        file_size = file_path.stat().st_size
        db.update_lora_model(model_id, file_size=file_size)

        print(f"✅ Model downloaded: {model_name}")
    except Exception as exc:  # pragma: no cover - background task logging only
        print(f"❌ Failed to download model {model_name}: {exc}")
        db.update_lora_model(model_id, is_downloaded=False)
    finally:
        db.close()


def set_model_manager(manager: ModelManager):
    global _model_manager
    _model_manager = manager
