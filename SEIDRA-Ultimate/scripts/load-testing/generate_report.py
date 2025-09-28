#!/usr/bin/env python3
"""Génère un résumé Markdown à partir des rapports CSV Locust."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class AggregatedStats:
    requests: int
    failures: int
    avg_response: float
    p95_response: Optional[float]
    requests_per_sec: float

    @property
    def success_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return (self.requests - self.failures) / self.requests * 100


@dataclass
class EndpointStats:
    name: str
    method: str
    requests: int
    failures: int
    avg_response: float
    p95_response: Optional[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthèse Markdown des rapports Locust")
    parser.add_argument("--reports-dir", required=True, help="Répertoire contenant les exports Locust")
    parser.add_argument("--basename", required=True, help="Préfixe des fichiers CSV Locust")
    parser.add_argument(
        "--output",
        help="Chemin du fichier Markdown généré (par défaut <reports-dir>/<basename>_summary.md)",
    )
    return parser.parse_args()


def _to_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def _to_float(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _extract_p95(row: dict[str, str]) -> Optional[float]:
    for key in ("95%", "95%ile", "95% Percentile"):
        if key in row and row[key]:
            return _to_float(row[key])
    return None


def load_aggregated(stats_rows: Iterable[dict[str, str]]) -> Optional[AggregatedStats]:
    for row in stats_rows:
        if row.get("Name") in {"Aggregated", "Total"}:
            return AggregatedStats(
                requests=_to_int(row.get("Requests")),
                failures=_to_int(row.get("Failures")),
                avg_response=_to_float(row.get("Average Response Time")),
                p95_response=_extract_p95(row),
                requests_per_sec=_to_float(row.get("Requests/s")),
            )
    return None


def load_endpoints(stats_rows: Iterable[dict[str, str]]) -> List[EndpointStats]:
    endpoints: List[EndpointStats] = []
    for row in stats_rows:
        if row.get("Type") not in {"Request", "request"}:
            continue
        name = row.get("Name") or "Inconnu"
        method = row.get("Method") or row.get("Method/Name", "-")
        endpoints.append(
            EndpointStats(
                name=name,
                method=method,
                requests=_to_int(row.get("Requests")),
                failures=_to_int(row.get("Failures")),
                avg_response=_to_float(row.get("Average Response Time")),
                p95_response=_extract_p95(row),
            )
        )
    endpoints.sort(key=lambda item: item.avg_response, reverse=True)
    return endpoints


def load_failures(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_stats(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def format_ms(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def build_markdown(
    basename: str,
    aggregated: Optional[AggregatedStats],
    endpoints: List[EndpointStats],
    failures: list[dict[str, str]],
) -> str:
    lines = [f"# Rapport synthétique Locust – {basename}", ""]

    if aggregated:
        lines.extend(
            [
                "## Vue d'ensemble",
                "",
                f"- Requêtes totales : **{aggregated.requests:,}**",
                f"- Échecs : **{aggregated.failures:,}**",
                f"- Taux de réussite : **{aggregated.success_rate:.2f}%**",
                f"- Temps de réponse moyen : **{aggregated.avg_response:.2f} ms**",
                f"- Temps de réponse 95e percentile : **{format_ms(aggregated.p95_response)} ms**",
                f"- Débit moyen : **{aggregated.requests_per_sec:.2f} req/s**",
                "",
            ]
        )
    else:
        lines.append("Aucune donnée agrégée disponible dans le rapport.")
        lines.append("")

    lines.extend(["## Top endpoints les plus lents", ""])
    if endpoints:
        lines.append("| Méthode | Endpoint | Requêtes | Échecs | Temps moyen (ms) | P95 (ms) |")
        lines.append("|---------|----------|----------|--------|------------------|----------|")
        for endpoint in endpoints[:5]:
            lines.append(
                f"| {endpoint.method} | {endpoint.name} | {endpoint.requests} | {endpoint.failures} | "
                f"{endpoint.avg_response:.2f} | {format_ms(endpoint.p95_response)} |"
            )
    else:
        lines.append("Aucun endpoint mesuré.")
    lines.append("")

    lines.extend(["## Erreurs principales", ""])
    if failures:
        lines.append("| Endpoint | Erreur | Occurrences |")
        lines.append("|----------|-------|-------------|")
        for failure in failures[:5]:
            name = failure.get("Name") or failure.get("name") or "Inconnu"
            error = failure.get("Error") or failure.get("error") or "N/A"
            occurrences = failure.get("Occurrences") or failure.get("occurrences") or "0"
            lines.append(f"| {name} | {error} | {occurrences} |")
    else:
        lines.append("Aucune erreur recensée.")
    lines.append("")

    lines.append("_Rapport généré automatiquement par `scripts/load-testing/generate_report.py`._")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    reports_dir = Path(args.reports_dir)
    basename = args.basename
    stats_path = reports_dir / f"{basename}_stats.csv"
    failures_path = reports_dir / f"{basename}_failures.csv"
    output_path = Path(args.output) if args.output else reports_dir / f"{basename}_summary.md"

    stats_rows = read_stats(stats_path)
    aggregated = load_aggregated(stats_rows)
    endpoints = load_endpoints(stats_rows)
    failures = load_failures(failures_path)

    markdown = build_markdown(basename, aggregated, endpoints, failures)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Rapport Markdown généré : {output_path}")


if __name__ == "__main__":
    main()
