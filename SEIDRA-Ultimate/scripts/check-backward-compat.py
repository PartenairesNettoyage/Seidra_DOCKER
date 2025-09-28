#!/usr/bin/env python3
"""Compare les contrats d'API Classic vs Ultimate pour garantir la compatibilité."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Tuple


def load_paths(path: Path) -> Dict[str, Dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("paths", {})  # type: ignore[return-value]


def diff_paths(reference: Dict[str, Dict[str, object]], candidate: Dict[str, Dict[str, object]]) -> Tuple[list[str], list[str]]:
    missing = [route for route in reference if route not in candidate]
    extra = [route for route in candidate if route not in reference]
    return sorted(missing), sorted(extra)


def diff_methods(reference: Dict[str, Dict[str, object]], candidate: Dict[str, Dict[str, object]]) -> Iterable[str]:
    for route, methods in reference.items():
        candidate_methods = candidate.get(route, {})
        for method in methods:
            if method not in candidate_methods:
                yield f"{route} -> {method.upper()} absent"


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérifie la compatibilité ascendante entre deux fichiers OpenAPI")
    parser.add_argument("reference", type=Path, help="Chemin vers l'OpenAPI de référence (plateforme classique)")
    parser.add_argument("candidate", type=Path, help="Chemin vers l'OpenAPI Ultimate à valider")
    args = parser.parse_args()

    if not args.reference.exists():
        raise SystemExit(f"Fichier de référence introuvable: {args.reference}")
    if not args.candidate.exists():
        raise SystemExit(f"Fichier Ultimate introuvable: {args.candidate}")

    reference_paths = load_paths(args.reference)
    candidate_paths = load_paths(args.candidate)

    missing_routes, extra_routes = diff_paths(reference_paths, candidate_paths)
    missing_methods = list(diff_methods(reference_paths, candidate_paths))

    if missing_routes or missing_methods:
        print("❌ Incompatibilités détectées :")
        for route in missing_routes:
            print(f"  - Route absente dans Ultimate: {route}")
        for entry in missing_methods:
            print(f"  - {entry}")
        return 1

    print("✅ Compatibilité ascendante confirmée")
    if extra_routes:
        print("ℹ️ Routes additionnelles présentes dans Ultimate :")
        for route in extra_routes:
            print(f"  - {route}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
