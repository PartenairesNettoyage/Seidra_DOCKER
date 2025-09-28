#!/usr/bin/env python3
"""Construit un script k6 prêt à l'emploi pour charger la génération vidéo."""
from __future__ import annotations

import argparse
from pathlib import Path
from textwrap import dedent


TEMPLATE = r"""
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    video_load: {
      executor: 'ramping-arrival-rate',
      startRate: %(start_rate)s,
      timeUnit: '1s',
      preAllocatedVUs: %(preallocated)s,
      maxVUs: %(max_vus)s,
      stages: [
        { target: %(arrival_rate)s, duration: '%(ramp)s' },
        { target: %(arrival_rate)s, duration: '%(steady)s' },
        { target: 0, duration: '%(cooldown)s' },
      ],
    },
  },
};

const BASE_URL = __ENV.SEIDRA_BASE_URL || 'http://localhost:8000';
const AUTH_HEADER = __ENV.SEIDRA_TOKEN ? { Authorization: `Bearer ${__ENV.SEIDRA_TOKEN}` } : {};
const VIDEO_DURATION = Number(__ENV.SEIDRA_VIDEO_DURATION || %(video_duration)s);
const PRIORITY = __ENV.SEIDRA_PRIORITY || '%(priority)s';

export default function () {
  const payload = JSON.stringify({
    prompt: `Video load test ${__ITER}`,
    duration_seconds: VIDEO_DURATION,
    priority: PRIORITY,
  });
  const res = http.post(
    `${BASE_URL.replace(/\/$/, '')}/api/v1/generation/video`,
    payload,
    { headers: { 'Content-Type': 'application/json', ...AUTH_HEADER } }
  );
  check(res, {
    'statut accepté': (r) => r.status === 202 || r.status === 200,
  });
  sleep(%(sleep)s);
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export d'un script k6 vidéo")
    parser.add_argument("--output", type=Path, required=True, help="Fichier de destination du script")
    parser.add_argument("--arrival-rate", type=int, default=6, help="Arrivées par seconde cible")
    parser.add_argument("--start-rate", type=int, default=2, help="Taux de départ")
    parser.add_argument("--preallocated", type=int, default=10, help="VUs pré-alloués")
    parser.add_argument("--max-vus", type=int, default=50, help="VUs maximum")
    parser.add_argument("--ramp", type=str, default="2m", help="Durée de montée en charge")
    parser.add_argument("--steady", type=str, default="5m", help="Durée du plateau")
    parser.add_argument("--cooldown", type=str, default="1m", help="Durée de descente")
    parser.add_argument("--video-duration", type=int, default=8, help="Durée des vidéos en secondes")
    parser.add_argument("--priority", type=str, default="batch", help="Priorité k6 envoyée")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pause entre deux requêtes")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    content = TEMPLATE % {
        "arrival_rate": args.arrival_rate,
        "start_rate": args.start_rate,
        "preallocated": args.preallocated,
        "max_vus": args.max_vus,
        "ramp": args.ramp,
        "steady": args.steady,
        "cooldown": args.cooldown,
        "video_duration": args.video_duration,
        "priority": args.priority,
        "sleep": args.sleep,
    }
    rendered = dedent(content).strip() + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Script k6 généré: {args.output}")


if __name__ == "__main__":
    main()
