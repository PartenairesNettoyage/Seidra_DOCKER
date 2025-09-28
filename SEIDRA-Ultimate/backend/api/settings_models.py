"""Shared schemas and defaults for settings-related endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "ultimate",
    "language": "en",
    "notifications": {
        "web": True,
        "email": False,
        "slack": False,
    },
    "telemetry_opt_in": True,
}


class SettingsResponse(BaseModel):
    theme: str = Field(default=DEFAULT_SETTINGS["theme"])
    language: str = Field(default=DEFAULT_SETTINGS["language"])
    notifications: Dict[str, bool] = Field(
        default_factory=lambda: DEFAULT_SETTINGS["notifications"].copy()
    )
    telemetry_opt_in: bool = Field(default=DEFAULT_SETTINGS["telemetry_opt_in"])
    extra: Dict[str, Any] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    theme: Optional[str] = None
    language: Optional[str] = None
    notifications: Optional[Dict[str, bool]] = None
    telemetry_opt_in: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = None


class NSFWSettingsPayload(BaseModel):
    enabled: bool = True
    age_verified: bool = False
    intensity: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    categories: Dict[str, bool] = Field(default_factory=dict)
    overrides: Dict[str, Any] = Field(default_factory=dict)

