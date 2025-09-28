"""Vérifie que le contrat OpenAPI Ultimate reste compatible avec la version Classic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import pytest

HTTP_METHODS = {"get", "put", "post", "delete", "patch", "options", "head"}
ROOT = Path(__file__).resolve().parents[2]
OPENAPI_DIR = ROOT / "openapi"


@pytest.fixture(scope="module")
def classic_spec() -> Dict[str, Any]:
    path = OPENAPI_DIR / "classic.json"
    if not path.exists():
        pytest.skip("Spécification Classic absente")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ultimate_spec() -> Dict[str, Any]:
    path = OPENAPI_DIR / "ultimate.json"
    if not path.exists():
        pytest.skip("Spécification Ultimate absente")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_operations(spec: Dict[str, Any]) -> Iterable[Tuple[str, str, Dict[str, Any]]]:
    paths = spec.get("paths", {})
    for route, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            yield route, method.lower(), operation


def is_subset(reference: Any, candidate: Any) -> bool:
    """Retourne True si ``reference`` est contenu dans ``candidate``."""

    if isinstance(reference, dict):
        if not isinstance(candidate, dict):
            return False
        return all(key in candidate and is_subset(value, candidate[key]) for key, value in reference.items())

    if isinstance(reference, list):
        if not isinstance(candidate, list):
            return False
        for ref_item in reference:
            if not any(is_subset(ref_item, cand_item) for cand_item in candidate):
                return False
        return True

    return reference == candidate


def test_paths_and_methods_are_backward_compatible(classic_spec: Dict[str, Any], ultimate_spec: Dict[str, Any]) -> None:
    ultimate_paths = ultimate_spec.get("paths", {})
    for route, method, classic_operation in iter_operations(classic_spec):
        assert route in ultimate_paths, f"Route absente dans Ultimate: {route}"
        ultimate_operation = ultimate_paths[route].get(method)
        assert ultimate_operation is not None, f"Méthode {method.upper()} absente pour {route}"
        assert is_subset(classic_operation, ultimate_operation), (
            f"Le contrat {method.upper()} {route} diffère entre Classic et Ultimate"
        )


def test_components_stay_backward_compatible(classic_spec: Dict[str, Any], ultimate_spec: Dict[str, Any]) -> None:
    classic_components = classic_spec.get("components", {})
    ultimate_components = ultimate_spec.get("components", {})

    for section in ("schemas", "responses", "parameters", "requestBodies"):
        classic_section = classic_components.get(section)
        if not isinstance(classic_section, dict):
            continue
        ultimate_section = ultimate_components.get(section, {})
        for name, definition in classic_section.items():
            assert name in ultimate_section, f"Composant {section}.{name} manquant dans Ultimate"
            assert is_subset(definition, ultimate_section[name]), (
                f"Composant {section}.{name} n'est plus rétrocompatible"
            )
