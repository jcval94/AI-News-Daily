"""Curated metadata-only music and SFX library. No network access or downloads."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from pipeline.schema_validation import validate_payload

DEFAULT_CATALOG = Path("catalog/audio/index.json")
BLOCKED = re.compile(
    r"all rights reserved|fair use|non[- ]commercial|\bcc[- ]?by[- ]?nc\b|"
    r"\bno derivatives\b|\bcc[- ]?by[- ]?nd\b|\bunknown\b",
    re.IGNORECASE,
)


def _https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            and not parsed.hostname.endswith(".local")
        )
    except ValueError:
        return False


def rights_status(item: dict[str, Any]) -> str:
    """Human approval is required; no license name implies automatic approval."""
    info = item["license"]
    review = item["rights_review"]
    if review["status"] == "rejected" or BLOCKED.search(info["identifier"]):
        return "blocked"
    if review["status"] != "approved":
        return "review_required"
    if not all(review.get(key) is True for key in (
        "commercial_use_confirmed", "synchronization_confirmed", "edits_confirmed"
    )):
        return "review_required"
    if not review.get("reviewer") or not review.get("reviewed_on"):
        return "review_required"
    return "approved"


def validate_catalog(payload: dict[str, Any]) -> dict[str, int]:
    validate_payload(payload, "audio_library.schema.json")
    seen: set[str] = set()
    counts = {"total": 0, "approved": 0, "review_required": 0, "blocked": 0}
    for item in payload["items"]:
        asset_id = item["id"]
        if asset_id in seen:
            raise ValueError(f"Duplicate audio id: {asset_id}")
        seen.add(asset_id)
        for field, value in (
            ("source_url", item["source_url"]),
            ("license.terms_url", item["license"]["terms_url"]),
            ("license.evidence_url", item["license"]["evidence_url"]),
        ):
            if not _https_url(value):
                raise ValueError(f"{asset_id}: unsafe or invalid {field}")
        try:
            date.fromisoformat(item["license"]["checked_on"])
            if item["rights_review"].get("reviewed_on"):
                date.fromisoformat(item["rights_review"]["reviewed_on"])
        except ValueError as error:
            raise ValueError(f"{asset_id}: invalid review/evidence date") from error
        if "local_relpath" in item:
            candidate = PurePosixPath(item["local_relpath"])
            if ".." in candidate.parts or "\\" in item["local_relpath"]:
                raise ValueError(f"{asset_id}: unsafe local_relpath")
        counts["total"] += 1
        counts[rights_status(item)] += 1
    return counts


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate audio catalog metadata without downloads")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    print(json.dumps(validate_catalog(json.loads(args.catalog.read_text(encoding="utf-8"))), sort_keys=True))


if __name__ == "__main__":
    main()
