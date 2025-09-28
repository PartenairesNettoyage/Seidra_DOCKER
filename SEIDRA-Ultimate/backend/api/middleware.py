"""Middlewares personnalisés pour l'API SEIDRA."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RateLimitQuotaMiddleware(BaseHTTPMiddleware):
    """Expose de manière homogène les politiques de quotas applicables."""

    def __init__(
        self,
        app,
        *,
        default_policy: str | None = None,
        scoped_policies: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(app)
        self._default_policy = default_policy
        scoped_policies = scoped_policies or {}
        # On trie par longueur pour capturer d'abord les préfixes les plus spécifiques.
        self._scoped_policies: list[tuple[str, str]] = sorted(
            scoped_policies.items(), key=lambda item: len(item[0]), reverse=True
        )

    def _iter_candidates(self, path: str) -> Iterable[str]:
        for prefix, policy in self._scoped_policies:
            if path.startswith(prefix):
                yield policy
        if self._default_policy:
            yield self._default_policy

    def _resolve_policy(self, path: str) -> str | None:
        return next(iter(self._iter_candidates(path)), None)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        policy = self._resolve_policy(request.url.path)
        if policy:
            request.state.rate_limit_policy = policy

        response: Response = await call_next(request)

        if not policy:
            return response

        response.headers.setdefault("X-RateLimit-Policy", policy)

        return response
