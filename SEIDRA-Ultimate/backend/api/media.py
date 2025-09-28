"""
SEIDRA Media API
Advanced gallery management with intelligent filtering
"""

import asyncio
import json
import mimetypes
import os
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path, PurePath
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import verify_token
from api.generation import VideoAssetWaveformResponse
from core.config import settings
from services.database import DatabaseService
from core.rate_limit import media_rate_limit_dependencies
from services.generation_service import get_generation_service
from workers.video_worker import generate_asset_waveform_task


EXPORT_BASE_DIR = (Path("../data/exports")).resolve()
VIDEO_ASSET_DIR = settings.media_directory / "video_assets"


def _ensure_within_export_dir(path: Path, base_dir: Path) -> None:
    resolved_base = base_dir.resolve()
    try:
        resolved_base.relative_to(EXPORT_BASE_DIR)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid export file location")

    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid export file location")


def _validate_export_filename(filename: str) -> None:
    if not filename or filename.strip() != filename:
        raise HTTPException(status_code=400, detail="Invalid export file name")

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid export file name")

    pure_path = PurePath(filename)
    if ".." in pure_path.parts:
        raise HTTPException(status_code=400, detail="Invalid export file name")

router = APIRouter(
    dependencies=[Depends(verify_token), *media_rate_limit_dependencies]
)
_generation_service = get_generation_service()
USE_CELERY = os.getenv("SEIDRA_USE_CELERY", "0") == "1"


async def _run_local_waveform(asset_id: str, sample_points: int = 128, force: bool = False):
    await _generation_service.generate_asset_waveform(
        asset_id,
        sample_points=sample_points,
        force=force,
    )


def _schedule_local_waveform(asset_id: str, sample_points: int = 128, force: bool = False):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_local_waveform(asset_id, sample_points, force))
    else:
        loop.create_task(_run_local_waveform(asset_id, sample_points, force))

# Request/Response models
class MediaFilters(BaseModel):
    tags: Optional[List[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    favorites_only: bool = False
    persona_id: Optional[int] = None
    search_query: Optional[str] = None

class MediaItemResponse(BaseModel):
    id: str
    user_id: int
    job_id: str
    file_path: str
    thumbnail_path: Optional[str]
    file_type: str
    mime_type: Optional[str]
    metadata: Dict[str, Any]
    tags: List[str]
    is_favorite: bool
    is_nsfw: bool
    nsfw_tags: List[str]
    created_at: str


class MediaListResponse(BaseModel):
    total: int
    items: List[MediaItemResponse]

class MediaStats(BaseModel):
    total_images: int
    total_size: str
    favorites_count: int
    recent_count: int
    by_persona: Dict[str, int]
    by_date: Dict[str, int]

class ExportRequest(BaseModel):
    media_ids: List[str]
    format: str = Field(default="zip")  # zip, json
    include_metadata: bool = True

class BulkAction(BaseModel):
    action: str  # delete, favorite, unfavorite, tag, untag
    media_ids: List[str]
    tags: Optional[List[str]] = None


class VideoAssetResponse(BaseModel):
    id: str
    name: str
    kind: str
    duration: float
    file_size: int
    status: str
    url: str
    download_url: str
    created_at: str
    mime_type: str


def _asset_metadata_path(asset_id: str) -> Path:
    return VIDEO_ASSET_DIR / f"{asset_id}.json"


def _load_asset_metadata(asset_id: str) -> Dict[str, Any]:
    metadata_path = _asset_metadata_path(asset_id)
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Video asset not found")
    try:
        return json.loads(metadata_path.read_text())
    except json.JSONDecodeError as exc:  # pragma: no cover - corrupted metadata
        raise HTTPException(status_code=500, detail="Corrupted asset metadata") from exc


def _detect_asset_kind(content_type: Optional[str], provided: Optional[str]) -> str:
    if provided:
        return provided
    if not content_type:
        return "video"
    if content_type.startswith("audio/"):
        return "audio"
    if content_type.startswith("image/"):
        return "image"
    return "video"


def _store_video_asset(
    *,
    upload: UploadFile,
    contents: bytes,
    duration: Optional[float],
    kind: Optional[str],
) -> VideoAssetResponse:
    VIDEO_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    asset_id = str(uuid.uuid4())
    file_size = len(contents)

    mime_type = upload.content_type or "application/octet-stream"
    extension = Path(upload.filename or "").suffix
    if not extension:
        guessed = mimetypes.guess_extension(mime_type)
        extension = guessed or ".bin"

    stored_path = VIDEO_ASSET_DIR / f"{asset_id}{extension}"
    stored_path.write_bytes(contents)

    normalized_duration = max(float(duration or 0.0), 0.1)
    detected_kind = _detect_asset_kind(mime_type, kind)
    created_at = datetime.utcnow().isoformat()

    metadata = {
        "id": asset_id,
        "original_name": upload.filename or stored_path.name,
        "mime_type": mime_type,
        "file_path": str(stored_path),
        "file_size": file_size,
        "duration": normalized_duration,
        "kind": detected_kind,
        "created_at": created_at,
    }
    _asset_metadata_path(asset_id).write_text(json.dumps(metadata))

    download_url = f"/api/media/video-assets/{asset_id}"
    return VideoAssetResponse(
        id=asset_id,
        name=metadata["original_name"],
        kind=detected_kind,
        duration=normalized_duration,
        file_size=file_size,
        status="ready",
        url=download_url,
        download_url=download_url,
        created_at=created_at,
        mime_type=mime_type,
    )


@router.post("/video-assets", response_model=VideoAssetResponse)
async def upload_video_asset(
    file: UploadFile = File(...),
    duration: Optional[float] = Form(None),
    kind: Optional[str] = Form(None),
    current_user=Depends(verify_token),
):
    try:
        contents = await file.read()
        return _store_video_asset(upload=file, contents=contents, duration=duration, kind=kind)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to store asset: {exc}") from exc


@router.get("/video-assets/{asset_id}")
async def download_video_asset(asset_id: str, current_user=Depends(verify_token)):
    metadata = _load_asset_metadata(asset_id)
    file_path = Path(metadata["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video asset file missing")

    return FileResponse(
        path=file_path,
        media_type=metadata.get("mime_type", "application/octet-stream"),
        filename=metadata.get("original_name", file_path.name),
    )


@router.get("/video-assets/{asset_id}/waveform", response_model=VideoAssetWaveformResponse)
async def get_video_asset_waveform(
    asset_id: str,
    background_tasks: BackgroundTasks,
    sample_points: int = Query(default=128, ge=16, le=2048),
    force: bool = Query(default=False),
    current_user=Depends(verify_token),
):
    try:
        metadata = _load_asset_metadata(asset_id)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    kind = (metadata.get("kind") or "audio").lower()
    if kind not in {"audio", "video"}:
        raise HTTPException(status_code=400, detail="Waveform unavailable for this asset type")

    if not metadata.get("file_path"):
        raise HTTPException(status_code=404, detail="Asset file missing for waveform generation")

    if not force:
        existing = _generation_service.load_asset_waveform(asset_id)
        if existing:
            return VideoAssetWaveformResponse(**{**existing, "status": "ready"})

    if USE_CELERY:
        background_tasks.add_task(
            generate_asset_waveform_task.delay,
            asset_id,
            sample_points,
            force,
        )
    else:
        background_tasks.add_task(
            _schedule_local_waveform,
            asset_id,
            sample_points,
            force,
        )

    return VideoAssetWaveformResponse(
        asset_id=asset_id,
        waveform=[],
        sample_rate=None,
        peak_amplitude=None,
        generated_at=None,
        status="processing",
    )

@router.get("/", response_model=MediaListResponse)
async def list_media(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    tags: Optional[str] = Query(default=None),
    favorites_only: bool = Query(default=False),
    search: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    persona_id: Optional[int] = Query(default=None),
    current_user=Depends(verify_token),
):
    """List media items with advanced filtering"""

    user_id = current_user.id
    db = DatabaseService()
    try:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        parsed_date_from = None
        parsed_date_to = None
        try:
            if date_from:
                parsed_date_from = datetime.fromisoformat(date_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_from format. Use ISO8601.")

        try:
            if date_to:
                parsed_date_to = datetime.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date_to format. Use ISO8601.")

        media_items, total = db.get_media_items(
            user_id=user_id,
            limit=limit,
            offset=offset,
            favorites_only=favorites_only,
            tags=tag_list,
            search=search,
            date_from=parsed_date_from,
            date_to=parsed_date_to,
            persona_id=persona_id,
        )

        return MediaListResponse(
            total=total,
            items=[
                MediaItemResponse(
                    id=item.id,
                    user_id=item.user_id,
                    job_id=item.job_id,
                    file_path=item.file_path,
                    thumbnail_path=item.thumbnail_path,
                    file_type=item.file_type,
                    mime_type=item.mime_type,
                    metadata=item.metadata_payload or {},
                    tags=item.tags or [],
                    is_favorite=item.is_favorite,
                    is_nsfw=item.is_nsfw,
                    nsfw_tags=item.nsfw_tags or [],
                    created_at=item.created_at.isoformat(),
                )
                for item in media_items
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list media: {str(e)}")
    finally:
        db.close()

@router.get("/stats", response_model=MediaStats)
async def get_media_stats(current_user=Depends(verify_token)):
    """Get media statistics"""

    db = DatabaseService()
    try:
        stats = db.get_media_statistics(current_user.id)
        total_size = f"{stats['total_size_bytes'] / (1024*1024):.1f}MB"
        return MediaStats(
            total_images=stats["total_images"],
            total_size=total_size,
            favorites_count=stats["favorites_count"],
            recent_count=stats["recent_count"],
            by_persona=stats["by_persona"],
            by_date=stats["by_date"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")
    finally:
        db.close()

@router.get("/{media_id}")
async def get_media_item(media_id: str, current_user=Depends(verify_token)):
    """Get specific media item"""

    db = DatabaseService()
    try:
        media_item = db.get_media_item(media_id, current_user.id)
        if not media_item:
            raise HTTPException(status_code=404, detail="Media item not found")

        return MediaItemResponse(
            id=media_item.id,
            user_id=media_item.user_id,
            job_id=media_item.job_id,
            file_path=media_item.file_path,
            thumbnail_path=media_item.thumbnail_path,
            file_type=media_item.file_type,
            mime_type=media_item.mime_type,
            metadata=media_item.metadata_payload or {},
            tags=media_item.tags or [],
            is_favorite=media_item.is_favorite,
            is_nsfw=media_item.is_nsfw,
            nsfw_tags=media_item.nsfw_tags or [],
            created_at=media_item.created_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get media item: {str(e)}")
    finally:
        db.close()

@router.get("/{media_id}/download")
async def download_media(media_id: str, current_user=Depends(verify_token)):
    """Download media file"""
    
    db = DatabaseService()
    try:
        media_item = db.get_media_item(media_id, current_user.id)
        if not media_item:
            raise HTTPException(status_code=404, detail="Media item not found")

        if not os.path.exists(media_item.file_path):
            raise HTTPException(status_code=404, detail="Media file not found")

        filename = os.path.basename(media_item.file_path)
        return FileResponse(
            media_item.file_path,
            filename=filename,
            media_type=media_item.mime_type or "application/octet-stream",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download media: {str(e)}")
    finally:
        db.close()

@router.put("/{media_id}/favorite")
async def toggle_favorite(media_id: str, current_user=Depends(verify_token)):
    """Toggle favorite status"""
    
    db = DatabaseService()
    try:
        media_item = db.get_media_item(media_id, current_user.id)
        if not media_item:
            raise HTTPException(status_code=404, detail="Media item not found")

        updated = db.update_media_item(
            media_id,
            current_user.id,
            is_favorite=not media_item.is_favorite,
            updated_at=datetime.utcnow(),
        )

        return {
            "media_id": media_id,
            "is_favorite": updated.is_favorite if updated else not media_item.is_favorite,
            "message": "Favorite status updated",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle favorite: {str(e)}")
    finally:
        db.close()

@router.put("/{media_id}/tags")
async def update_tags(media_id: str, tags: List[str], current_user=Depends(verify_token)):
    """Update media item tags"""
    
    db = DatabaseService()
    try:
        media_item = db.get_media_item(media_id, current_user.id)
        if not media_item:
            raise HTTPException(status_code=404, detail="Media item not found")

        updated = db.update_media_item(
            media_id,
            current_user.id,
            tags=tags,
            updated_at=datetime.utcnow(),
        )

        return {
            "media_id": media_id,
            "tags": updated.tags if updated else tags,
            "message": "Tags updated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update tags: {str(e)}")
    finally:
        db.close()

@router.delete("/{media_id}")
async def delete_media(media_id: str, current_user=Depends(verify_token)):
    """Delete media item"""
    
    db = DatabaseService()
    try:
        success = db.delete_media_item(media_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Media item not found")
        
        return {"message": "Media item deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete media: {str(e)}")
    finally:
        db.close()

@router.post("/bulk-action")
async def bulk_action(action_request: BulkAction, current_user=Depends(verify_token)):
    """Perform bulk action on multiple media items"""

    if not action_request.media_ids:
        raise HTTPException(status_code=400, detail="No media IDs provided")

    if action_request.action in {"tag", "untag"} and not action_request.tags:
        raise HTTPException(status_code=400, detail="Tags payload required for tagging actions")

    db = DatabaseService()
    try:
        results = {
            "action": action_request.action,
            "processed": 0,
            "failed": 0,
            "media_ids": action_request.media_ids
        }
        
        for media_id in action_request.media_ids:
            try:
                if action_request.action == "delete":
                    success = db.delete_media_item(media_id, current_user.id)
                    if success:
                        results["processed"] += 1
                    else:
                        results["failed"] += 1

                elif action_request.action in ["favorite", "unfavorite"]:
                    desired_state = action_request.action == "favorite"
                    updated = db.update_media_item(media_id, current_user.id, is_favorite=desired_state)
                    if updated:
                        results["processed"] += 1
                    else:
                        results["failed"] += 1

                elif action_request.action in ["tag", "untag"]:
                    if action_request.tags is None:
                        raise HTTPException(status_code=400, detail="Tags payload required")

                    media_item = db.get_media_item(media_id, current_user.id)
                    if not media_item:
                        results["failed"] += 1
                        continue

                    current_tags = set(media_item.tags or [])
                    tag_set = set(action_request.tags)
                    if action_request.action == "tag":
                        new_tags = list(current_tags.union(tag_set))
                    else:
                        new_tags = [tag for tag in current_tags if tag not in tag_set]

                    updated = db.update_media_item(media_id, current_user.id, tags=new_tags)
                    if updated:
                        results["processed"] += 1
                    else:
                        results["failed"] += 1

                else:
                    results["failed"] += 1

            except HTTPException:
                raise
            except Exception as e:
                print(f"Failed to process {media_id}: {e}")
                results["failed"] += 1
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk action failed: {str(e)}")
    finally:
        db.close()

@router.post("/export")
async def export_media(export_request: ExportRequest, current_user=Depends(verify_token)):
    """Export selected media items"""
    
    if not export_request.media_ids:
        raise HTTPException(status_code=400, detail="No media IDs provided")
    
    db = DatabaseService()
    try:
        # Get media items
        media_items, _ = db.get_media_items(user_id=current_user.id, limit=10000)
        selected_items = [
            item for item in media_items
            if item.id in export_request.media_ids
        ]
        
        if not selected_items:
            raise HTTPException(status_code=404, detail="No valid media items found")
        
        # Create export directory
        export_dir = (EXPORT_BASE_DIR / str(current_user.id)).resolve()
        _ensure_within_export_dir(export_dir, EXPORT_BASE_DIR)
        export_dir.mkdir(parents=True, exist_ok=True)

        export_filename = f"seidra_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        export_path = (export_dir / export_filename).resolve()
        _ensure_within_export_dir(export_path, export_dir)
        
        # Create ZIP file
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in selected_items:
                if os.path.exists(item.file_path):
                    # Add image file
                    filename = f"{item.id}_{os.path.basename(item.file_path)}"
                    zipf.write(item.file_path, filename)
                    
                    # Add metadata if requested
                    if export_request.include_metadata:
                        metadata_filename = f"{item.id}_metadata.json"
                        metadata = {
                            "id": item.id,
                            "job_id": item.job_id,
                            "tags": item.tags,
                            "is_favorite": item.is_favorite,
                            "created_at": item.created_at.isoformat(),
                            "metadata": item.metadata_payload
                        }
                        zipf.writestr(metadata_filename, json.dumps(metadata, indent=2))
        
        return {
            "export_file": export_filename,
            "download_url": f"/api/media{router.url_path_for('download_export', filename=export_filename)}",
            "items_count": len(selected_items),
            "file_size": f"{export_path.stat().st_size / (1024*1024):.1f}MB"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        db.close()

@router.get("/download-export/{filename}")
async def download_export(filename: str, current_user=Depends(verify_token)):
    """Download export file"""

    _validate_export_filename(filename)

    export_dir = (EXPORT_BASE_DIR / str(current_user.id)).resolve()
    _ensure_within_export_dir(export_dir, EXPORT_BASE_DIR)
    export_path = (export_dir / filename).resolve()
    _ensure_within_export_dir(export_path, export_dir)

    if not export_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    
    return FileResponse(
        export_path,
        filename=filename,
        media_type="application/zip"
    )
