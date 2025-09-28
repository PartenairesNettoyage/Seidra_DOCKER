"""Scénarios de tests de charge Locust pour l'API SEIDRA Ultimate."""

from __future__ import annotations

import base64
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from locust import HttpUser, between, events, task

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PATH = REPO_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from core.config import secret_manager

API_URL = secret_manager.get("SEIDRA_API_URL")
JWT_TOKEN = secret_manager.get("SEIDRA_JWT")

if API_URL is not None and not isinstance(API_URL, str):
    raise RuntimeError("Le secret SEIDRA_API_URL doit être une chaîne de caractères.")

if JWT_TOKEN is not None and not isinstance(JWT_TOKEN, str):
    raise RuntimeError("Le secret SEIDRA_JWT doit être une chaîne de caractères.")

if not API_URL:
    raise RuntimeError(
        "Le secret SEIDRA_API_URL doit être défini (variable d'environnement, Vault ou SSM)."
    )

if not JWT_TOKEN:
    raise RuntimeError(
        "Le secret SEIDRA_JWT doit être défini (variable d'environnement, Vault ou SSM)."
    )

API_URL = str(API_URL)
JWT_TOKEN = str(JWT_TOKEN)

REPORT_DIR = Path(os.getenv("REPORT_DIR", "/opt/locust/reports"))
REPORT_BASENAME = os.getenv("REPORT_BASENAME", "seidra_loadtest")

SILENCE_WAV = base64.b64decode(
    "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="
)

PROMPTS: List[str] = [
    "Portrait réaliste d'une astronaute regardant la Terre depuis l'orbite",
    "Dragon cyberpunk se posant sur un gratte-ciel au coucher du soleil",
    "Illustration minimaliste d'un robot assistant dans un bureau moderne",
]


def _percentile(stats_entry, percentile: float) -> float:
    response_times: Dict[int, int] = getattr(stats_entry, "response_times", {})
    if not response_times:
        return 0.0

    total_requests = sum(response_times.values())
    if total_requests == 0:
        return 0.0

    threshold = total_requests * percentile
    cumulative = 0
    for response_time in sorted(response_times):
        cumulative += response_times[response_time]
        if cumulative >= threshold:
            return float(response_time)
    return float(stats_entry.max_response_time or 0.0)


class SeidraUser(HttpUser):
    host = API_URL.rstrip("/")
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.json_headers = {
            "Authorization": f"Bearer {JWT_TOKEN}",
        }
        self.form_headers = {
            "Authorization": f"Bearer {JWT_TOKEN}",
        }

    @task(4)
    def generate_single_image(self) -> None:
        width, height = random.choice([(1024, 1024), (768, 1344), (1344, 768)])
        payload = {
            "prompt": random.choice(PROMPTS),
            "negative_prompt": "",
            "width": width,
            "height": height,
            "num_inference_steps": random.choice([25, 30, 40]),
            "guidance_scale": 7.5,
            "num_images": 1,
            "model_name": "sdxl-base",
            "scheduler": "ddim",
            "style": None,
            "quality": "high",
            "job_type": "image",
            "metadata": {"source": "load-test"},
        }
        with self.client.post(
            "/api/generate/single",
            json=payload,
            headers=self.json_headers,
            name="POST /api/generate/single",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                detail = response.text[:200]
                response.failure(f"Statut inattendu {response.status_code}: {detail}")

    @task(1)
    def list_media(self) -> None:
        with self.client.get(
            "/api/media?limit=20",
            headers=self.json_headers,
            name="GET /api/media",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                detail = response.text[:200]
                response.failure(f"Statut inattendu {response.status_code}: {detail}")

    @task(1)
    def generate_video(self) -> None:
        data = {
            "prompt": random.choice(PROMPTS),
            "duration_seconds": 6,
            "model_name": "sadtalker",
            "metadata": json.dumps({"source": "load-test"}),
        }
        files = {
            "audio_file": ("silence.wav", SILENCE_WAV, "audio/wav"),
        }
        with self.client.post(
            "/api/generate/video",
            data=data,
            files=files,
            headers=self.form_headers,
            name="POST /api/generate/video",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                detail = response.text[:200]
                response.failure(f"Statut inattendu {response.status_code}: {detail}")


@events.quitting.add_listener
def _write_summary(environment, **_kwargs) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = REPORT_DIR / f"{REPORT_BASENAME}_summary.md"

    total_stats = environment.stats.total
    total_requests = total_stats.num_requests
    total_failures = total_stats.num_failures
    success_count = total_requests - total_failures

    start_time = environment.stats.start_time or 0.0
    last_request = total_stats.last_request_timestamp or start_time
    duration = max(0.0, last_request - start_time)
    avg_rps = (total_requests / duration) if duration else 0.0
    fail_rate = (total_failures / total_requests * 100.0) if total_requests else 0.0

    lines = [
        f"# Rapport de test de charge ({datetime.utcnow().isoformat()}Z)",
        "",
        f"- Hôte cible : `{environment.host or 'inconnu'}`",
        f"- Durée approximative : {duration:.1f} s",
        f"- Requêtes réussies : {success_count}",
        f"- Requêtes en échec : {total_failures} ({fail_rate:.2f} %)",
        f"- Débit moyen estimé : {avg_rps:.2f} req/s",
        "",
        "## Détails par endpoint",
        "",
        "| Requête | Nombre | Échecs | Temps moyen (ms) | Min (ms) | Max (ms) | p95 (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def iter_stats() -> Iterable:
        for stats in environment.stats.entries.values():
            if stats.num_requests == 0:
                continue
            yield stats

    for stats in sorted(iter_stats(), key=lambda s: (s.method, s.name)):
        p95 = _percentile(stats, 0.95)
        lines.append(
            "| {name} | {count} | {fails} | {avg:.1f} | {min:.1f} | {max:.1f} | {p95:.1f} |".format(
                name=f"{stats.method} {stats.name}",
                count=stats.num_requests,
                fails=stats.num_failures,
                avg=stats.avg_response_time,
                min=stats.min_response_time or 0.0,
                max=stats.max_response_time or 0.0,
                p95=p95,
            )
        )

    lines.append("")
    lines.append("*Test exécuté automatiquement via `make loadtest`.*")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
