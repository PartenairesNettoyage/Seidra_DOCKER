#!/usr/bin/env python3
"""Valide les tableaux de bord Grafana et vérifie la disponibilité des endpoints d'observabilité."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import requests
import yaml


@dataclass
class DatasourceRegistry:
    names: set[str]
    uids: set[str]

    def describe(self) -> str:
        names = ", ".join(sorted(self.names)) or "aucun"
        uids = ", ".join(sorted(self.uids)) or "aucun"
        return f"noms = [{names}] / UID = [{uids}]"

    def contains(self, name: str | None, uid: str | None) -> bool:
        if uid and uid in self.uids:
            return True
        if name and name in self.names:
            return True
        return False


@dataclass
class ValidationIssue:
    location: str
    message: str

    def __str__(self) -> str:
        return f"[{self.location}] {self.message}"


def load_datasource_registry(provisioning_dir: Path) -> DatasourceRegistry:
    datasources_file = provisioning_dir / "datasources" / "datasources.yml"
    if not datasources_file.exists():
        raise FileNotFoundError(
            f"Fichier de provisioning introuvable: {datasources_file}"
        )

    content = yaml.safe_load(datasources_file.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(
            f"Format inattendu pour {datasources_file} (attendu: dictionnaire YAML)"
        )

    raw_datasources: Sequence[object] = content.get("datasources", [])  # type: ignore[assignment]

    names: set[str] = set()
    uids: set[str] = set()
    for entry in raw_datasources:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            names.add(name)
        uid = entry.get("uid")
        if isinstance(uid, str) and uid:
            uids.add(uid)

    return DatasourceRegistry(names=names, uids=uids)


def iter_panels(dashboard: dict[str, object]) -> Iterable[dict[str, object]]:
    stack: list[dict[str, object]] = [panel for panel in dashboard.get("panels", []) if isinstance(panel, dict)]  # type: ignore[list-item]
    while stack:
        panel = stack.pop()
        yield panel
        nested = panel.get("panels")
        if isinstance(nested, list):
            stack.extend([child for child in nested if isinstance(child, dict)])


def extract_reference(ref: object) -> tuple[str | None, str | None]:
    if ref is None:
        return None, None
    if isinstance(ref, str):
        value = ref.strip()
        if not value:
            return None, None
        return value, None
    if isinstance(ref, dict):
        name = ref.get("name") if isinstance(ref.get("name"), str) else None
        uid = ref.get("uid") if isinstance(ref.get("uid"), str) else None
        return name, uid
    return None, None


def validate_dashboard(
    path: Path, registry: DatasourceRegistry
) -> tuple[list[str], list[ValidationIssue]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    references: list[str] = []
    issues: list[ValidationIssue] = []

    def register_reference(name: str | None, uid: str | None, context: str) -> None:
        if not name and not uid:
            issues.append(ValidationIssue(context, "aucune datasource référencée"))
            return
        if not registry.contains(name, uid):
            display = f"name={name!r} uid={uid!r}"
            issues.append(
                ValidationIssue(context, f"datasource inconnue ({display}). Sources disponibles: {registry.describe()}")
            )
        else:
            display = name or uid or "<inconnu>"
            references.append(display)

    for panel in iter_panels(data):
        title = panel.get("title") if isinstance(panel.get("title"), str) else "panel sans titre"
        panel_ctx = f"panel '{title}'"
        panel_ds = extract_reference(panel.get("datasource"))
        if panel_ds != (None, None):
            register_reference(*panel_ds, context=f"{panel_ctx} (datasource)")

        targets = panel.get("targets")
        if isinstance(targets, list):
            for target in targets:
                if not isinstance(target, dict):
                    continue
                ref_id = target.get("refId") if isinstance(target.get("refId"), str) else "?"
                ctx = f"{panel_ctx} -> cible {ref_id}"
                target_ds = extract_reference(target.get("datasource"))
                if target_ds == (None, None):
                    if panel_ds == (None, None):
                        issues.append(ValidationIssue(ctx, "datasource manquante"))
                    continue
                register_reference(*target_ds, context=ctx)

    templating = data.get("templating")
    if isinstance(templating, dict):
        templating_list = templating.get("list")
        if isinstance(templating_list, list):
            for variable in templating_list:
                if not isinstance(variable, dict):
                    continue
                name = variable.get("name") if isinstance(variable.get("name"), str) else "variable"
                ctx = f"variable '{name}'"
                variable_ds = extract_reference(variable.get("datasource"))
                if variable_ds == (None, None):
                    continue
                register_reference(*variable_ds, context=ctx)

    return references, issues


def check_http_endpoint(
    name: str,
    url: str,
    timeout: float,
    max_attempts: int,
    delay: float,
    require: bool,
) -> tuple[bool, str]:
    last_error: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code >= 400:
                last_error = f"code HTTP {response.status_code}"
            else:
                return True, f"Endpoint {name} joignable ({url})"
        except requests.RequestException as exc:  # pragma: no cover - dépend du réseau
            last_error = str(exc)
        if attempt < max_attempts:
            time.sleep(delay)
    if require:
        return False, f"Endpoint {name} injoignable ({url}): {last_error}"
    return True, f"Endpoint {name} ignoré (stack non disponible ? {last_error})"


def parse_args() -> argparse.Namespace:
    default_monitoring = Path(__file__).resolve().parents[2] / "monitoring"
    parser = argparse.ArgumentParser(description="Vérifie la configuration Grafana/Prometheus")
    parser.add_argument(
        "--monitoring-dir",
        type=Path,
        default=default_monitoring,
        help="Répertoire racine contenant monitoring/",
    )
    parser.add_argument(
        "--prometheus-url",
        default="http://localhost:9090/-/ready",
        help="Endpoint HTTP de Prometheus à vérifier",
    )
    parser.add_argument(
        "--grafana-url",
        default="http://localhost:3001/api/health",
        help="Endpoint HTTP de Grafana à vérifier",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=2.0,
        help="Timeout (s) pour les requêtes HTTP",
    )
    parser.add_argument(
        "--http-retries",
        type=int,
        default=5,
        help="Nombre de tentatives pour les vérifications HTTP",
    )
    parser.add_argument(
        "--http-delay",
        type=float,
        default=2.0,
        help="Attente (s) entre les tentatives HTTP",
    )
    parser.add_argument(
        "--require-http",
        action="store_true",
        help="Échoue si les endpoints HTTP sont injoignables",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    monitoring_dir = args.monitoring_dir.resolve()
    grafana_dir = monitoring_dir / "grafana"
    provisioning_dir = grafana_dir / "provisioning"

    if not grafana_dir.exists():
        print(f"❌ Répertoire Grafana introuvable: {grafana_dir}")
        return 1

    try:
        registry = load_datasource_registry(provisioning_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 1

    dashboard_files = [
        path for path in grafana_dir.rglob("*.json") if path.is_file()
    ]

    if not dashboard_files:
        print("⚠️ Aucun tableau de bord Grafana (*.json) trouvé")
        return 1

    overall_ok = True
    for dashboard_path in dashboard_files:
        references, issues = validate_dashboard(dashboard_path, registry)
        if issues:
            overall_ok = False
            print(f"❌ {dashboard_path.relative_to(monitoring_dir)}")
            for issue in issues:
                print(f"   - {issue}")
        else:
            refs = ", ".join(sorted(set(references))) or "aucune référence"
            print(f"✅ {dashboard_path.relative_to(monitoring_dir)} -> datasources détectées: {refs}")

    ok_prometheus, msg_prometheus = check_http_endpoint(
        "Prometheus",
        args.prometheus_url,
        timeout=args.http_timeout,
        max_attempts=args.http_retries,
        delay=args.http_delay,
        require=args.require_http,
    )
    print(("✅ " if ok_prometheus else "❌ ") + msg_prometheus)
    if not ok_prometheus:
        overall_ok = False

    ok_grafana, msg_grafana = check_http_endpoint(
        "Grafana",
        args.grafana_url,
        timeout=args.http_timeout,
        max_attempts=args.http_retries,
        delay=args.http_delay,
        require=args.require_http,
    )
    print(("✅ " if ok_grafana else "❌ ") + msg_grafana)
    if not ok_grafana:
        overall_ok = False

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
