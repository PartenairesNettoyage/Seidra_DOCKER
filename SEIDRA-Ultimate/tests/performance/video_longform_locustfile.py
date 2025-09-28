"""Scénario Locust simulant des vidéos longue durée via SadTalker/ComfyUI."""

from __future__ import annotations

import base64
import json
import math
import os
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests
from locust import HttpUser, between, events, task


PROMPTS: List[str] = [
    "Documentaire immersif sur une exploration lunaire, narration posée et ton cinématographique",
    "Annonce produit avec animateur virtuel dans un studio néon, rythme énergique",
    "Tutoriel de méditation guidée au lever du soleil avec avatar réaliste et ambiance douce",
]

TOKEN = os.getenv("SEIDRA_PERF_TOKEN", "changeme")
HOST = os.getenv("SEIDRA_PERF_HOST", "http://localhost:8000").rstrip("/")
MODEL_NAME = os.getenv("SEIDRA_PERF_VIDEO_MODEL", "sadtalker")

TOTAL_MIN_SECONDS = int(os.getenv("SEIDRA_PERF_VIDEO_TOTAL_MIN", "180"))
TOTAL_MAX_SECONDS = int(os.getenv("SEIDRA_PERF_VIDEO_TOTAL_MAX", "420"))
SEGMENT_SECONDS = int(os.getenv("SEIDRA_PERF_VIDEO_SEGMENT", "45"))
TELEMETRY_WINDOW_MINUTES = int(os.getenv("SEIDRA_PERF_VIDEO_TELEMETRY_MINUTES", "180"))
HTTP_TIMEOUT = float(os.getenv("SEIDRA_PERF_TIMEOUT", "30"))

PIPELINE_PRESET = os.getenv("SEIDRA_PERF_VIDEO_PIPELINE", "comfyui-longform-v1")
VOICE_PRESET = os.getenv("SEIDRA_PERF_VIDEO_VOICE", "sadtalker-conversation")

REPORT_DIR = Path(
    os.getenv(
        "SEIDRA_PERF_REPORT_DIR",
        Path(__file__).resolve().parents[2] / "reports" / "perf",
    )
)
REPORT_BASENAME = os.getenv("SEIDRA_PERF_REPORT_NAME", "video_longform")

SILENCE_WAV = base64.b64decode(
    "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="
)


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


@dataclass
class MetricsRecorder:
    """Collecte des métriques GPU et vidéo au fil du test."""

    submitted_jobs: List[Dict[str, Any]] = field(default_factory=list)
    generation_snapshot: Dict[str, Any] = field(default_factory=dict)
    gpu_snapshot: Dict[str, Any] = field(default_factory=dict)
    cuda_errors: List[Dict[str, Any]] = field(default_factory=list)

    def register_job(
        self,
        *,
        job_id: str,
        target_duration: int,
        segment_duration: int,
        segment_count: int,
    ) -> None:
        self.submitted_jobs.append(
            {
                "job_id": job_id,
                "target_duration": target_duration,
                "segment_duration": segment_duration,
                "segment_count": segment_count,
            }
        )

    def ingest_generation_metrics(self, payload: Dict[str, Any]) -> None:
        self.generation_snapshot = payload
        recent = payload.get("recent") or []
        self.cuda_errors = []
        for item in recent:
            errors = item.get("cudaErrors") or []
            if isinstance(errors, dict):
                self.cuda_errors.append(errors)
            elif isinstance(errors, list):
                self.cuda_errors.extend(errors)

    def ingest_system_snapshot(self, payload: Dict[str, Any]) -> None:
        snapshot = payload.get("snapshot") or {}
        if snapshot:
            self.gpu_snapshot = snapshot.get("gpu", {})

    def _format_locust_table(self, environment) -> List[str]:
        lines = [
            "| Requête | Nombre | Échecs | Temps moyen (ms) | Min (ms) | Max (ms) | p95 (ms) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]

        def iter_stats() -> Iterable:
            for stats in environment.stats.entries.values():
                if stats.num_requests == 0:
                    continue
                yield stats

        for stats in sorted(iter_stats(), key=lambda item: (item.method, item.name)):
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
        return lines

    def _format_generation_section(self) -> List[str]:
        summary = self.generation_snapshot.get("summary", {})
        items = self.generation_snapshot.get("items", [])

        latencies = [
            item.get("latencySeconds")
            for item in items
            if isinstance(item.get("latencySeconds"), (int, float))
        ]
        peaks = [
            item.get("vramPeakMb")
            for item in items
            if isinstance(item.get("vramPeakMb"), (int, float))
        ]

        section = ["## Télémetrie vidéo", ""]
        section.append(
            "- Durée moyenne (seconds) : {avg}".format(
                avg=_format_optional_float(summary.get("averageDurationSeconds"))
            )
        )
        section.append(
            "- Pic VRAM moyen (MB) : {peak}".format(
                peak=_format_optional_float(summary.get("averagePeakVramMb"))
            )
        )
        section.append(
            "- Débit moyen (frames/s) : {throughput}".format(
                throughput=_format_optional_float(summary.get("averageThroughput"))
            )
        )
        section.append(
            "- Mesures collectées : {count}".format(count=len(items))
        )

        if latencies:
            section.append(
                "- p95 latence (seconds) : {value}".format(
                    value=_format_optional_float(_percentile_from_list(latencies, 0.95))
                )
            )
        if peaks:
            section.append(
                "- Pic VRAM max observé (MB) : {value}".format(value=int(max(peaks)))
            )

        if self.cuda_errors:
            section.append("")
            section.append("### Erreurs GPU récentes")
            for error in self.cuda_errors:
                message = error.get("message") if isinstance(error, dict) else str(error)
                timestamp = error.get("timestamp") if isinstance(error, dict) else "inconnu"
                section.append(f"- {timestamp}: {message}")
        else:
            section.append("")
            section.append("### Erreurs GPU récentes")
            section.append("- Aucune erreur CUDA signalée sur la fenêtre analysée.")

        return section

    def _format_gpu_section(self) -> List[str]:
        if not self.gpu_snapshot:
            return ["## Statut GPU", "", "- Télémetrie indisponible."]

        section = ["## Statut GPU", ""]
        memory_used = self.gpu_snapshot.get("memory_used") or self.gpu_snapshot.get("memoryUsed")
        memory_total = self.gpu_snapshot.get("memory_total") or self.gpu_snapshot.get("memoryTotal")
        inference_avg = self.gpu_snapshot.get("inference_avg_seconds")
        cuda_error_count = self.gpu_snapshot.get("cuda_error_count")

        section.append(
            "- VRAM utilisée : {used} MB / {total} MB".format(
                used=_format_optional_float(memory_used),
                total=_format_optional_float(memory_total),
            )
        )
        section.append(
            "- Latence moyenne rolling : {value} s".format(
                value=_format_optional_float(inference_avg)
            )
        )
        section.append(
            "- Compteur d'erreurs CUDA : {count}".format(
                count=str(cuda_error_count) if cuda_error_count is not None else "inconnu"
            )
        )
        return section

    def write_report(self, environment) -> None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / f"{REPORT_BASENAME}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.md"

        total_stats = environment.stats.total
        total_requests = total_stats.num_requests
        total_failures = total_stats.num_failures
        success_count = total_requests - total_failures

        start_time = environment.stats.start_time or 0.0
        last_request = total_stats.last_request_timestamp or start_time
        duration = max(0.0, last_request - start_time)
        avg_rps = (total_requests / duration) if duration else 0.0
        fail_rate = (total_failures / total_requests * 100.0) if total_requests else 0.0

        job_count = len(self.submitted_jobs)
        target_durations = [job["target_duration"] for job in self.submitted_jobs]
        segment_counts = [job["segment_count"] for job in self.submitted_jobs]
        segment_duration = min(SEGMENT_SECONDS, 60)

        if target_durations:
            duration_min = min(target_durations)
            duration_max = max(target_durations)
        else:
            duration_min = TOTAL_MIN_SECONDS
            duration_max = TOTAL_MAX_SECONDS

        if segment_counts:
            avg_segments = sum(segment_counts) / len(segment_counts)
            max_segments = max(segment_counts)
        else:
            avg_segments = 0.0
            max_segments = 0

        lines = [
            f"# Rapport charge vidéo longue durée ({datetime.utcnow().isoformat()}Z)",
            "",
            "## Paramètres de test",
            "",
            f"- Hôte cible : `{HOST}`",
            f"- Modèle vidéo : `{MODEL_NAME}`",
            f"- Durée cible par scénario : {duration_min}–{duration_max} s",
            f"- Durée segment envoyée : {segment_duration} s",
            f"- Jobs soumis : {job_count}",
            f"- Segments par job : moyenne {avg_segments:.1f} (max {max_segments})",
            "",
            "## Statistiques Locust",
            "",
            f"- Requêtes réussies : {success_count}",
            f"- Requêtes en échec : {total_failures} ({fail_rate:.2f} %)",
            f"- Débit moyen estimé : {avg_rps:.2f} req/s",
            "",
        ]
        lines.extend(self._format_locust_table(environment))
        lines.append("")
        lines.extend(self._format_generation_section())
        lines.append("")
        lines.extend(self._format_gpu_section())
        lines.append("")
        lines.append("*Rapport généré automatiquement par `video_longform_locustfile.py`.*")

        path.write_text("\n".join(lines), encoding="utf-8")


RECORDER = MetricsRecorder()


def _format_optional_float(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return "n/a"


def _percentile_from_list(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(ordered[int(index)])
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower))


class SeidraVideoUser(HttpUser):
    """Utilisateur long-forme visant les pipelines ComfyUI/SadTalker."""

    host = HOST
    wait_time = between(5, 15)

    def on_start(self) -> None:  # pragma: no cover - exécuté par Locust uniquement
        self.form_headers = {"Authorization": f"Bearer {TOKEN}"}

    @task(1)
    def generate_long_video(self) -> None:
        target_duration = random.randint(TOTAL_MIN_SECONDS, TOTAL_MAX_SECONDS)
        segment_duration = min(SEGMENT_SECONDS, 60)
        segment_count = max(1, math.ceil(target_duration / segment_duration))

        metadata = {
            "source": "performance-longform",
            "pipeline": PIPELINE_PRESET,
            "voicePreset": VOICE_PRESET,
            "targetDurationSeconds": target_duration,
            "segmentDurationSeconds": segment_duration,
            "segmentCount": segment_count,
        }

        data = {
            "prompt": random.choice(PROMPTS),
            "duration_seconds": str(segment_duration),
            "model_name": MODEL_NAME,
            "metadata": json.dumps(metadata),
        }
        files = {
            "audio_file": ("silence.wav", SILENCE_WAV, "audio/wav"),
        }

        with self.client.post(
            "/api/generate/video",
            data=data,
            files=files,
            headers=self.form_headers,
            name="POST /api/generate/video (longform)",
            timeout=HTTP_TIMEOUT,
            catch_response=True,
        ) as response:
            if response.status_code not in (200, 202):
                detail = response.text[:200]
                response.failure(
                    f"Statut inattendu {response.status_code}: {detail}"
                )
                return

            try:
                payload: Dict[str, Any] = response.json()
            except ValueError:
                response.failure("Réponse JSON invalide")
                return

            job_id = payload.get("job_id") or payload.get("jobId")
            if isinstance(job_id, str):
                RECORDER.register_job(
                    job_id=job_id,
                    target_duration=target_duration,
                    segment_duration=segment_duration,
                    segment_count=segment_count,
                )
            response.success()


def _fetch_generation_metrics() -> Optional[Dict[str, Any]]:
    url = f"{HOST}/api/system/telemetry/generation"
    params = {"minutes": TELEMETRY_WINDOW_MINUTES, "media_type": "video"}
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    if response.status_code != 200:
        return None
    return response.json()


def _fetch_system_snapshot() -> Optional[Dict[str, Any]]:
    url = f"{HOST}/api/system/telemetry"
    params = {"minutes": TELEMETRY_WINDOW_MINUTES}
    headers = {"Authorization": f"Bearer {TOKEN}"}
    response = requests.get(url, params=params, headers=headers, timeout=HTTP_TIMEOUT)
    if response.status_code != 200:
        return None
    return response.json()


@events.quitting.add_listener
def _write_longform_report(environment, **_kwargs) -> None:
    try:
        generation_metrics = _fetch_generation_metrics()
        if generation_metrics:
            RECORDER.ingest_generation_metrics(generation_metrics)
    except requests.RequestException as exc:  # pragma: no cover - dépend du réseau
        print(f"⚠️ Impossible de récupérer la télémetrie vidéo : {exc}")

    try:
        system_snapshot = _fetch_system_snapshot()
        if system_snapshot:
            RECORDER.ingest_system_snapshot(system_snapshot)
    except requests.RequestException as exc:  # pragma: no cover - dépend du réseau
        print(f"⚠️ Impossible de récupérer la télémetrie GPU : {exc}")

    RECORDER.write_report(environment)
