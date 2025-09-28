"""Tests d'intégration pour la limitation de débit."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import pytest


class _InMemoryRedis:
    def __init__(self) -> None:
        self._store: dict[str, tuple[int, float]] = {}
        self._script_id = "in-memory"

    async def script_load(self, script: str) -> str:  # noqa: ARG002 - compat signature
        self._lua = script
        return self._script_id

    async def evalsha(self, sha: str, _numkeys: int, key: str, times: str, milliseconds: str) -> int:
        if sha != self._script_id:
            raise RuntimeError("script SHA inconnu")

        quota = int(times)
        window_ms = int(milliseconds)
        now = time.monotonic()
        count, expires_at = self._store.get(key, (0, now + window_ms / 1000.0))

        if expires_at <= now:
            count = 0
            expires_at = now + window_ms / 1000.0

        if count + 1 > quota:
            ttl_ms = max(int((expires_at - now) * 1000), 1)
            return ttl_ms

        self._store[key] = (count + 1, expires_at)
        return 0

    async def close(self) -> None:  # pragma: no cover - symétrie API
        self._store.clear()


@pytest.fixture()
def rate_limited_client():
    redis = _InMemoryRedis()

    app = FastAPI()
    policy = SimpleNamespace(
        global_quota=3,
        global_window_seconds=1,
        user_quota=2,
        user_window_seconds=1,
    )

    async def fake_verify_token(request: Request):
        user_header = request.headers.get("x-user", "1")
        user_id = int(user_header)
        request.state.authenticated_user_id = user_id
        return SimpleNamespace(id=user_id)

    router_dependencies = [Depends(fake_verify_token)] + _build_rate_limit_dependencies(
        policy, scope="tests"
    )
    router = APIRouter(dependencies=router_dependencies)

    @router.get("/limited")
    async def limited_endpoint(
        _user: Annotated[SimpleNamespace, Depends(fake_verify_token)]
    ) -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    @app.on_event("startup")
    async def startup() -> None:  # pragma: no cover - évènement implicite
        await FastAPILimiter.init(redis, prefix="test-rate")

    @app.on_event("shutdown")
    async def shutdown() -> None:  # pragma: no cover - évènement implicite
        try:
            await FastAPILimiter.close()
        finally:
            FastAPILimiter.redis = None

    with TestClient(app) as client:
        yield client


def _client_token(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "inconnu"


def _wrap_limiter(limiter: RateLimiter) -> Depends:
    async def dependency(request: Request, response: Response) -> None:
        if FastAPILimiter.redis is None:
            return None
        await limiter(request, response)

    return Depends(dependency)


def _build_rate_limit_dependencies(policy: SimpleNamespace, scope: str) -> list[Depends]:
    dependencies: list[Depends] = []

    if policy.global_quota and policy.global_window_seconds:
        async def global_identifier(request: Request) -> str:
            return f"{scope}:global:{_client_token(request)}"

        dependencies.append(
            _wrap_limiter(
                RateLimiter(
                    times=policy.global_quota,
                    seconds=policy.global_window_seconds,
                    identifier=global_identifier,
                )
            )
        )

    if policy.user_quota and policy.user_window_seconds:
        async def user_identifier(request: Request) -> str:
            user_id = getattr(request.state, "authenticated_user_id", None)
            if user_id is not None:
                return f"{scope}:user:{user_id}"
            return f"{scope}:anon:{_client_token(request)}"

        dependencies.append(
            _wrap_limiter(
                RateLimiter(
                    times=policy.user_quota,
                    seconds=policy.user_window_seconds,
                    identifier=user_identifier,
                )
            )
        )

    return dependencies


def _hit(client: TestClient, user: int) -> int:
    response = client.get("/limited", headers={"X-User": str(user)})
    return response.status_code


def test_user_limit_triggers_429(rate_limited_client: TestClient):
    client = rate_limited_client

    assert _hit(client, 7) == 200
    assert _hit(client, 7) == 200
    assert _hit(client, 7) == 429


def test_limit_resets_after_window(rate_limited_client: TestClient):
    client = rate_limited_client

    assert _hit(client, 2) == 200
    assert _hit(client, 2) == 200
    assert _hit(client, 2) == 429

    time.sleep(1.2)

    assert _hit(client, 2) == 200

