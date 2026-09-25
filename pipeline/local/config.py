from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pipeline.schema_validation import validate_payload

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRIVATE_CONFIG = REPO_ROOT / ".local" / "local_config.json"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "local" / "local_config.example.json"


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    config_path = Path(path).expanduser() if path else DEFAULT_PRIVATE_CONFIG
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Local config not found: {config_path}. Run python -m pipeline.local init first."
        )
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Local config must be a JSON object")
    validate_payload(payload, "local/local_config.schema.json")
    return payload


def resolve_executable(
    configured: str | None,
    *,
    executable_name: str,
    repo_root: Path = REPO_ROOT,
) -> Path | None:
    value = str(configured or "auto").strip()
    if value == "auto":
        found = shutil.which(executable_name)
        return Path(found).resolve() if found else None
    path = Path(value).expanduser()
    path = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    return path if path.is_file() else None


def initialize_private_config(*, force: bool = False) -> Path:
    destination = DEFAULT_PRIVATE_CONFIG
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        return destination
    destination.write_text(EXAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    return destination
