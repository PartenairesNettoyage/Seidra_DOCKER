#!/usr/bin/env python3
"""Génère un scénario de charge Celery pour les jobs vidéo SadTalker.

Le script produit un plan JSON décrivant la cadence d'envoi des tâches. Il peut
optionnellement publier les tâches vers Celery lorsqu'on utilise `--dispatch`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


@dataclass
class VideoJobScenario:
    job_id: str
    eta_seconds: float
    priority: str
    payload: Dict[str, object]


def build_scenario(
    *,
    concurrency: int,
    duration_seconds: int,
    prompt: str,
    priority: str,
    interval_seconds: float,
) -> List[VideoJobScenario]:
    jobs: List[VideoJobScenario] = []
    total_jobs = int(math.ceil(duration_seconds / interval_seconds) * max(concurrency, 1))
    for index in range(total_jobs):
        lane = index % max(concurrency, 1)
        eta = lane * (interval_seconds / max(concurrency, 1)) + (index // max(concurrency, 1)) * interval_seconds
        job_id = f"video-load-{index:05d}"
        payload = {
            "prompt": f"{prompt} #{index}",
            "duration_seconds": 8,
            "model_name": "sadtalker",
            "reference_image": None,
            "audio_artifact": {
                "filename": "sample.wav",
                "encoding": "base64",
                "data": "",
            },
            "_priority_tag": priority,
        }
        jobs.append(
            VideoJobScenario(
                job_id=job_id,
                eta_seconds=round(max(0.0, eta), 3),
                priority=priority,
                payload=payload,
            )
        )
    return jobs


def export_plan(jobs: List[VideoJobScenario], output: Optional[Path]) -> Path:
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "jobCount": len(jobs),
        "jobs": [asdict(job) for job in jobs],
    }
    if output is None:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return Path("-")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def maybe_dispatch(jobs: List[VideoJobScenario], countdown_offset: float) -> int:
    try:
        from workers.celery_app import celery_app
        from workers.generation_worker import _resolve_queue_config  # type: ignore
    except Exception as exc:  # pragma: no cover - dépend des dépendances locales
        print(f"⚠️ Impossible de dispatcher les tâches Celery: {exc}")
        return 0

    dispatched = 0
    for job in jobs:
        queue_name, priority_value = _resolve_queue_config(job.priority)
        countdown = max(0.0, job.eta_seconds + countdown_offset)
        celery_app.send_task(
            "workers.video_worker.generate_video_task",
            args=[job.job_id, job.payload],
            queue=queue_name,
            priority=priority_value,
            countdown=countdown,
        )
        dispatched += 1
    return dispatched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scénario de charge vidéo Celery")
    parser.add_argument("--output", type=Path, help="Fichier de sortie JSON", default=None)
    parser.add_argument("--concurrency", type=int, default=4, help="Nombre de voies parallèles")
    parser.add_argument("--duration", type=int, default=120, help="Durée de la campagne en secondes")
    parser.add_argument("--interval", type=float, default=12.0, help="Intervalle cible entre deux lots")
    parser.add_argument("--prompt", type=str, default="Demo video load", help="Prompt de base")
    parser.add_argument("--priority", type=str, default="batch", help="Priorité à appliquer")
    parser.add_argument("--dispatch", action="store_true", help="Publier les tâches vers Celery")
    parser.add_argument(
        "--countdown-offset",
        type=float,
        default=0.0,
        help="Décalage supplémentaire appliqué au countdown lors de l'envoi",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    jobs = build_scenario(
        concurrency=max(1, args.concurrency),
        duration_seconds=max(1, args.duration),
        prompt=args.prompt,
        priority=args.priority,
        interval_seconds=max(1.0, float(args.interval)),
    )
    output_path = export_plan(jobs, args.output)
    dispatched = 0
    if args.dispatch:
        dispatched = maybe_dispatch(jobs, args.countdown_offset)
    print(
        json.dumps(
            {
                "status": "ok",
                "jobs": len(jobs),
                "output": str(output_path),
                "dispatched": dispatched,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
