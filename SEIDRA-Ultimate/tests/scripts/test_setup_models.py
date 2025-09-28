"""Tests pour le script setup-models."""

import importlib.util
import runpy
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "setup-models.py"


def test_setup_models_echoue_si_dependances_absentes(monkeypatch, capsys):
    """Le script doit s'interrompre proprement lorsque les bibliothèques Hugging Face manquent."""

    original_find_spec = importlib.util.find_spec

    def faux_find_spec(name, package=None):
        if name in {"huggingface_hub", "diffusers", "torch"}:
            return None
        return original_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", faux_find_spec)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")

    assert excinfo.value.code == 1

    sortie = capsys.readouterr().out
    assert "Dépendances manquantes" in sortie
    assert "huggingface_hub" in sortie
    assert "pip install" in sortie
