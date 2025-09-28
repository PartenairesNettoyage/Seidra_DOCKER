"""
SEIDRA Backend - FastAPI Application
Premium AI Content Generation Platform
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from redis.asyncio import from_url as redis_from_url

from api.generation import router as generation_router, set_generation_service
from api.personas import router as personas_router
from api.models import router as models_router, set_model_manager
from api.media import router as media_router
from api.jobs import router as jobs_router
from api.settings import router as settings_router
from api.system import (
    router as system_router,
    set_gpu_monitor as set_system_gpu_monitor,
    set_model_manager as set_system_model_manager,
    set_telemetry_service as set_system_telemetry_service,
    set_notification_service as set_system_notification_service,
)
from api.auth import router as auth_router
from api.middleware import RateLimitQuotaMiddleware
from core.config import ensure_runtime_directories, settings
from services.database import get_default_user_last_rotation, init_database
from services.websocket_manager import WebSocketManager
from services.model_manager import ModelManager
from services.gpu_monitor import GPUMonitor
from services.generation_service import configure_generation_service
from services.notifications import NotificationService
from services.telemetry_service import TelemetryService

websocket_manager = WebSocketManager()
model_manager = ModelManager()
gpu_monitor = GPUMonitor()
notification_service = NotificationService(websocket_manager=websocket_manager)
model_manager.attach_notification_service(notification_service)
telemetry_service = TelemetryService(
    gpu_monitor=gpu_monitor,
    model_manager=model_manager,
    websocket_manager=websocket_manager,
    notification_service=notification_service,
)
model_manager.attach_telemetry_service(telemetry_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🌟 SEIDRA Backend Starting...")

    ensure_runtime_directories(settings)
    await init_database()
    print("✅ Database initialized")

    rate_limit_ready = False
    rate_limit_redis = None
    app.state.rate_limit_ready = False
    app.state.rate_limit_redis = None
    try:
        rate_limit_redis = redis_from_url(
            settings.rate_limit_redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await FastAPILimiter.init(rate_limit_redis, prefix=settings.rate_limit_redis_prefix)
        app.state.rate_limit_redis = rate_limit_redis
        app.state.rate_limit_ready = True
        rate_limit_ready = True
        print("✅ Limiteur de débit connecté à Redis")
    except Exception as exc:
        print(f"⚠️ Impossible de contacter Redis pour le rate limiting : {exc}")
        app.state.rate_limit_ready = False
        app.state.rate_limit_redis = None
        if rate_limit_redis is not None:
            await rate_limit_redis.close()
            rate_limit_redis = None

    service = configure_generation_service(
        model_manager,
        websocket_manager,
        notification_service,
        telemetry_service=telemetry_service,
    )
    set_generation_service(service)
    set_model_manager(model_manager)
    set_system_model_manager(model_manager)
    set_system_gpu_monitor(gpu_monitor)
    set_system_telemetry_service(telemetry_service)
    set_system_notification_service(notification_service)

    rotation_days = settings.default_user_rotation_days
    if rotation_days > 0:
        last_rotation = await asyncio.to_thread(get_default_user_last_rotation)
        now = datetime.now(timezone.utc)
        overdue = last_rotation is None or (now - last_rotation) >= timedelta(days=rotation_days)
        if overdue:
            await notification_service.push(
                "warning",
                "Rotation du compte démo requise",
                (
                    "Le mot de passe du compte démo doit être renouvelé. "
                    "Exécutez `make rotate-demo-user`, stockez le secret généré et "
                    "mettez à jour la variable SEIDRA_DEFAULT_USER_PASSWORD."
                ),
                category="security",
                tags=["security", "default-user"],
            )

    await model_manager.initialize()
    service._initialized = True
    print("✅ AI Models loaded")

    await gpu_monitor.start_monitoring()
    print("✅ GPU monitoring started")

    await telemetry_service.start()
    print("✅ Telemetry service running")

    print("🚀 SEIDRA Backend ready!")

    yield

    print("🛑 SEIDRA Backend shutting down...")
    if rate_limit_ready:
        try:
            await FastAPILimiter.close()
        except Exception:
            pass
    await gpu_monitor.stop_monitoring()
    await model_manager.cleanup()
    await telemetry_service.stop()


app = FastAPI(
    title="SEIDRA API",
    description="Premium AI Content Generation Platform - Build your own myth",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.debug,
)

app.add_middleware(
    RateLimitQuotaMiddleware,
    default_policy=settings.rate_limit_default,
    scoped_policies={
        "/api/generate": settings.rate_limit_generation,
        "/api/media": settings.rate_limit_media,
        "/api/auth": settings.rate_limit_auth,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ensure_runtime_directories(settings)
app.mount("/media", StaticFiles(directory=settings.media_directory), name="media")

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(generation_router, prefix="/api/generate", tags=["Generation"])
app.include_router(personas_router, prefix="/api/personas", tags=["Personas"])
app.include_router(models_router, prefix="/api/models", tags=["Models"])
app.include_router(media_router, prefix="/api/media", tags=["Media"])
app.include_router(jobs_router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
app.include_router(system_router, prefix="/api/system", tags=["System"])



@app.get("/")
async def root():
    return {
        "message": "SEIDRA API - Build your own myth",
        "version": "1.0.0",
        "status": "mystical",
    }


@app.get("/api/health")
async def health_check():
    gpu_status = await gpu_monitor.get_status()
    return {
        "status": "healthy",
        "gpu": gpu_status,
        "models_loaded": len(model_manager.loaded_models) if hasattr(model_manager, "loaded_models") else 0,
        "active_connections": len(websocket_manager.active_connections),
    }


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    token = websocket.query_params.get("token")
    if settings.websocket_token and token != settings.websocket_token:
        await websocket.close(code=1008)
        return

    user_id_param = websocket.query_params.get("userId")
    try:
        user_id = int(user_id_param) if user_id_param is not None else None
    except ValueError:
        user_id = None

    channels_param = websocket.query_params.get("channels")
    initial_channels = None
    if channels_param:
        initial_channels = {
            channel.strip()
            for channel in channels_param.split(",")
            if channel.strip()
        }

    await websocket_manager.connect(
        websocket, client_id, user_id=user_id, channels=initial_channels
    )
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
                if not isinstance(payload, dict):
                    raise ValueError("Invalid payload")
            except (ValueError, json.JSONDecodeError):
                payload = {"type": message.strip()} if message.strip() else None

            if not payload:
                await websocket_manager.send_personal_message(
                    {
                        "type": "error",
                        "message": "Invalid message payload.",
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    client_id,
                )
                continue

            await websocket_manager.handle_client_message(client_id, payload)
    except WebSocketDisconnect:
        websocket_manager.disconnect(client_id)
    except Exception:
        websocket_manager.disconnect(client_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
