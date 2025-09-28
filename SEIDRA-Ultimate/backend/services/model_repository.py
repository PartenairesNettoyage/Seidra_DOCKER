"""Utilities for managing model assets for the SEIDRA Ultimate stack.

The :class:`ModelRepository` centralises the logic for downloading checkpoints
and LoRA files required by the generation pipelines. The implementation is
async-friendly so it can be reused by the :class:`ModelManager` during the
Celery warm-up stage without blocking the event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, Callable

import httpx


DownloadConfig = Dict[str, Any]


class DownloadError(RuntimeError):
    """Raised when an asset cannot be downloaded or fails checksum validation."""


class ModelRepository:
    """Handle download and validation of model assets (checkpoints, LoRA)."""

    def __init__(
        self,
        models_dir: Path,
        *,
        http_client_factory: Optional[Callable[[], httpx.AsyncClient]] = None,
    ) -> None:
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._http_client_factory = http_client_factory or self._default_client_factory
        self._download_lock = asyncio.Lock()

    def _default_client_factory(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(120.0, connect=10.0, read=120.0)
        return httpx.AsyncClient(timeout=timeout)

    async def ensure_assets(self, assets: Dict[str, DownloadConfig]) -> Dict[str, Path]:
        """Ensure that the provided assets are available locally.

        Parameters
        ----------
        assets:
            Mapping where keys are logical asset identifiers and values are
            dictionaries containing at minimum ``url`` and ``filename``.

        Returns
        -------
        dict
            Mapping of asset identifiers to the resolved local file paths.
        """

        results: Dict[str, Path] = {}
        async with self._download_lock:
            async with self._http_client_factory() as client:
                for asset_id, config in assets.items():
                    local_path = self._resolve_destination(config)
                    checksum = config.get("sha256")
                    if local_path.exists() and (not checksum or self._check_checksum(local_path, checksum)):
                        results[asset_id] = local_path
                        continue

                    url = config.get("url")
                    if not url:
                        raise DownloadError(f"Asset {asset_id} is missing a download URL")

                    await self._download_file(client, url, local_path)
                    if checksum and not self._check_checksum(local_path, checksum):
                        local_path.unlink(missing_ok=True)
                        raise DownloadError(
                            f"Checksum mismatch for {asset_id} (expected {checksum})"
                        )

                    results[asset_id] = local_path
        return results

    async def _download_file(
        self,
        client: httpx.AsyncClient,
        url: str,
        destination: Path,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with destination.open("wb") as file_handle:
                async for chunk in response.aiter_bytes():
                    file_handle.write(chunk)

    def _resolve_destination(self, config: DownloadConfig) -> Path:
        relative_dir = Path(config.get("relative_dir") or config.get("category") or "misc")
        filename = config.get("filename")
        if not filename:
            raise DownloadError("Asset configuration missing filename")
        return self.models_dir / relative_dir / filename

    def _check_checksum(self, file_path: Path, expected: str) -> bool:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower() == expected.lower()
