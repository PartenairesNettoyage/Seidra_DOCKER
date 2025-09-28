"""User and NSFW settings endpoints for SEIDRA Ultimate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth import verify_token
from api.settings_models import (
    DEFAULT_SETTINGS,
    NSFWSettingsPayload,
    SettingsResponse,
    SettingsUpdate,
)
from services.database import DatabaseService

router = APIRouter()


@router.get("/", response_model=SettingsResponse)
async def get_settings(current_user=Depends(verify_token)):
    db = DatabaseService()
    try:
        user = db.get_user(current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        payload = {**DEFAULT_SETTINGS, **(user.settings or {})}
        extra = payload.get("extra", {})
        return SettingsResponse(
            theme=payload.get("theme", DEFAULT_SETTINGS["theme"]),
            language=payload.get("language", DEFAULT_SETTINGS["language"]),
            notifications=payload.get("notifications", DEFAULT_SETTINGS["notifications"]),
            telemetry_opt_in=payload.get("telemetry_opt_in", DEFAULT_SETTINGS["telemetry_opt_in"]),
            extra=extra,
        )
    finally:
        db.close()


@router.put("/", response_model=SettingsResponse)
async def update_settings(settings_update: SettingsUpdate, current_user=Depends(verify_token)):
    db = DatabaseService()
    try:
        updates = {k: v for k, v in settings_update.dict(exclude_unset=True).items() if v is not None}
        user = db.update_user_settings(current_user.id, **updates)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        payload = {**DEFAULT_SETTINGS, **(user.settings or {})}
        extra = payload.get("extra", {})
        return SettingsResponse(
            theme=payload.get("theme", DEFAULT_SETTINGS["theme"]),
            language=payload.get("language", DEFAULT_SETTINGS["language"]),
            notifications=payload.get("notifications", DEFAULT_SETTINGS["notifications"]),
            telemetry_opt_in=payload.get("telemetry_opt_in", DEFAULT_SETTINGS["telemetry_opt_in"]),
            extra=extra,
        )
    finally:
        db.close()


@router.get("/nsfw", response_model=NSFWSettingsPayload)
async def get_nsfw_settings(current_user=Depends(verify_token)):
    db = DatabaseService()
    try:
        record = db.get_nsfw_settings(user_id=current_user.id) or db.get_nsfw_settings(user_id=None)
        if not record:
            raise HTTPException(status_code=404, detail="NSFW settings not found")
        return NSFWSettingsPayload(
            enabled=record.enabled,
            age_verified=record.age_verified,
            intensity=record.intensity,
            categories=record.categories or {},
            overrides=record.overrides or {},
        )
    finally:
        db.close()


@router.put("/nsfw", response_model=NSFWSettingsPayload)
async def update_nsfw_settings(payload: NSFWSettingsPayload, current_user=Depends(verify_token)):
    db = DatabaseService()
    try:
        record = db.upsert_nsfw_settings(
            user_id=current_user.id,
            enabled=payload.enabled,
            age_verified=payload.age_verified,
            intensity=payload.intensity,
            categories=payload.categories,
            overrides=payload.overrides,
        )
        return NSFWSettingsPayload(
            enabled=record.enabled,
            age_verified=record.age_verified,
            intensity=record.intensity,
            categories=record.categories or {},
            overrides=record.overrides or {},
        )
    finally:
        db.close()
