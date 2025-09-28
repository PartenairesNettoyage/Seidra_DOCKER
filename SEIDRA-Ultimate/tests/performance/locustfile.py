"""Plan de test de charge Locust pour l'API SEIDRA."""

from __future__ import annotations

import json
import os
from typing import Any

from locust import HttpUser, between, events, task


PROMPT = os.getenv(
    "SEIDRA_PERF_PROMPT",
    "Portrait mystique dans une forêt embrumée, style illustration cinématographique",
)
MODEL_NAME = os.getenv("SEIDRA_PERF_MODEL", "sdxl-base")
TOKEN = os.getenv("SEIDRA_PERF_TOKEN", "changeme")
ENABLE_GENERATION = os.getenv("SEIDRA_PERF_ENABLE_GENERATION", "1") == "1"
GENERATION_ENDPOINT = os.getenv("SEIDRA_PERF_GENERATION_ENDPOINT", "/api/generate/single")
MEDIA_LIST_ENDPOINT = os.getenv("SEIDRA_PERF_MEDIA_LIST_ENDPOINT", "/api/media")
MEDIA_STATS_ENDPOINT = os.getenv("SEIDRA_PERF_MEDIA_STATS_ENDPOINT", "/api/media/stats")
TIMEOUT_SECONDS = float(os.getenv("SEIDRA_PERF_TIMEOUT", "30"))


class SeidraUser(HttpUser):
    """Utilisateur virtuel simulant les parcours critiques."""

    wait_time = between(1, 5)

    def on_start(self) -> None:  # pragma: no cover - exécuté par Locust uniquement
        self.client.headers.update({
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        })

    @task(3)
    def list_media(self) -> None:
        self.client.get(
            MEDIA_LIST_ENDPOINT,
            name="Media - liste",
            timeout=TIMEOUT_SECONDS,
        )

    @task(1)
    def media_stats(self) -> None:
        self.client.get(
            MEDIA_STATS_ENDPOINT,
            name="Media - stats",
            timeout=TIMEOUT_SECONDS,
        )

    @task(2)
    def trigger_generation(self) -> None:
        if not ENABLE_GENERATION:
            events.request.fire(
                request_type="GEN",
                name="Generation désactivée",
                response_time=0,
                response_length=0,
                exception=None,
                context={},
            )
            return

        payload: dict[str, Any] = {
            "prompt": PROMPT,
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
            "num_images": 1,
            "model_name": MODEL_NAME,
        }
        with self.client.post(
            GENERATION_ENDPOINT,
            name="Generation - single",
            data=json.dumps(payload),
            timeout=TIMEOUT_SECONDS,
            catch_response=True,
        ) as response:
            if response.status_code not in (200, 202):
                response.failure(
                    f"Réponse inattendue ({response.status_code}) : {response.text[:200]}"
                )
            else:
                response.success()


events.init.add_listener(
    lambda environment, **_kwargs: environment.events.quitting.add_listener(  # pragma: no cover
        lambda **__kwargs: print("Arrêt du test de charge SEIDRA")
    )
)
