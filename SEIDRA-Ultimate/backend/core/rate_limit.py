"""Outils de configuration du rate limiter FastAPI."""

from __future__ import annotations

from typing import Callable, List

from fastapi import Depends, Request, Response
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

from core.config import RateLimitPolicy, settings


def _client_token(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "inconnu"


def _build_global_identifier(scope: str) -> Callable[[Request], str]:
    async def identifier(request: Request) -> str:
        return f"{scope}:global:{_client_token(request)}"

    return identifier


def _build_user_identifier(scope: str) -> Callable[[Request], str]:
    async def identifier(request: Request) -> str:
        user_id = getattr(request.state, "authenticated_user_id", None)
        if user_id is not None:
            return f"{scope}:user:{user_id}"
        return f"{scope}:anon:{_client_token(request)}"

    return identifier


def _wrap_rate_limiter(limiter: RateLimiter) -> Depends:
    async def dependency(request: Request, response: Response) -> None:
        if FastAPILimiter.redis is None:
            return None
        await limiter(request, response)

    return Depends(dependency)


def build_rate_limit_dependencies(policy: RateLimitPolicy, scope: str) -> List[Depends]:
    """Construit les dépendances FastAPI appliquant la politique indiquée."""

    dependencies: List[Depends] = []

    if policy.global_quota > 0 and policy.global_window_seconds > 0:
        dependencies.append(
            _wrap_rate_limiter(
                RateLimiter(
                    times=policy.global_quota,
                    seconds=policy.global_window_seconds,
                    identifier=_build_global_identifier(scope),
                )
            )
        )

    if policy.user_quota > 0 and policy.user_window_seconds > 0:
        dependencies.append(
            _wrap_rate_limiter(
                RateLimiter(
                    times=policy.user_quota,
                    seconds=policy.user_window_seconds,
                    identifier=_build_user_identifier(scope),
                )
            )
        )

    return dependencies


default_rate_limit_dependencies = build_rate_limit_dependencies(
    settings.rate_limit_default_policy,
    scope="default",
)
"""Dépendances applicables à l'ensemble de l'API."""


generation_rate_limit_dependencies = build_rate_limit_dependencies(
    settings.rate_limit_generation_policy,
    scope="generation",
)
"""Dépendances communes pour les routes de génération."""


media_rate_limit_dependencies = build_rate_limit_dependencies(
    settings.rate_limit_media_policy,
    scope="media",
)
"""Dépendances communes pour les routes média."""


auth_rate_limit_dependencies = build_rate_limit_dependencies(
    settings.rate_limit_auth_policy,
    scope="auth",
)
"""Dépendances communes pour l'authentification."""

