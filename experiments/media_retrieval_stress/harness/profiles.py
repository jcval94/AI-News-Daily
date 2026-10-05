"""Experiment profile loading for the isolated stress lab."""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import validate as validate_contract
from .models import ExperimentProfile


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parent
PROFILES_ROOT = LAB_ROOT / "profiles"
DEFAULT_PROFILE = PROFILES_ROOT / "core_strict.json"


def load_profile(path: Path) -> ExperimentProfile:
    resolved = path.resolve()
    if not resolved.is_relative_to(PROFILES_ROOT.resolve()):
        raise ValueError("stress profiles must live inside experiments/media_retrieval_stress/profiles")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    validate_contract("experiment_profile.schema.json", payload)
    return ExperimentProfile.model_validate(payload)
