"""Curated metadata-only music and SFX library. No network access or downloads."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
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


def _license_traits(identifier: str) -> dict[str, bool]:
    """Classify obvious CC obligations and restrictions, never grant rights by name."""
    normalized = unicodedata.normalize("NFKC", identifier).casefold()
    words = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    forbidden = bool(re.search(
        r"\b(?:nc|nd|noncommercial|non commercial|non monetized|"
        r"not for commercial use|no derivatives?|no derivs?|"
        r"all rights reserved|fair use|unlicensed|no license|"
        r"unknown|unspecified|no restrictions)\b", words,
    ))
    cc_like = bool(re.search(r"\bcc\b|\bcc0\b|creative commons", words))
    cc0 = bool(re.search(r"\bcc0\b|\bcc zero\b|creative commons zero", words))
    attribution = cc_like and bool(re.search(
        r"\bcc by\b|creative commons attribution", words
    ))
    share_alike = attribution and bool(re.search(
        r"\bsa\b|share alike|sharealike", words
    ))
    supported_cc = cc0 or attribution
    return {
        "forbidden": forbidden or (cc_like and not supported_cc),
        "cc_like": cc_like,
        "attribution": attribution,
        "share_alike": share_alike,
    }


def rights_status(item: dict[str, Any]) -> str:
    """Fail closed for unattended use; the final grant is reviewed track by track."""
    info = item["license"]
    review = item["rights_review"]
    traits = _license_traits(info["identifier"])
    if review["status"] == "rejected" or traits["forbidden"]:
        return "blocked"
    if review["status"] != "approved":
        return "review_required"
    if not all(review.get(key) is True for key in (
        "commercial_use_confirmed", "synchronization_confirmed", "edits_confirmed",
        "track_specific_evidence_confirmed",
    )):
        return "review_required"
    if not review.get("reviewer") or not review.get("reviewed_on"):
        return "review_required"
    if "youtube" not in review.get("usage_platforms", []):
        return "review_required"
    if len(review.get("evidence_description", "").strip()) < 25:
        return "review_required"
    if review.get("attribution_required") is not True and traits["attribution"]:
        return "review_required"
    if traits["attribution"] and not info.get("attribution_text", "").strip():
        return "review_required"
    if traits["share_alike"] and review.get("share_alike_obligations_acknowledged") is not True:
        return "review_required"
    if traits["cc_like"] and review.get("rights_basis") != "creative_commons":
        return "review_required"
    if not traits["cc_like"] and review.get("rights_basis") == "creative_commons":
        return "review_required"
    if review.get("rights_basis") == "direct_permission" and not review.get("permission_record_url"):
        return "review_required"
    if review.get("content_id_review") in (None, "unchecked", "active_claim"):
        return "review_required"
    if (review.get("content_id_review") == "possible_claim"
            and review.get("content_id_risk_accepted") is not True):
        return "review_required"
    if review.get("attribution_required") is True and not info.get("attribution_text", "").strip():
        return "review_required"
    if review.get("preview_redistribution_allowed") not in (True, False):
        return "review_required"
    try:
        if date.fromisoformat(info["checked_on"]) > date.fromisoformat(review["reviewed_on"]):
            return "review_required"
    except (TypeError, ValueError, KeyError):
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
        url_fields = [
            ("source_url", item["source_url"]),
            ("license.terms_url", item["license"]["terms_url"]),
            ("license.evidence_url", item["license"]["evidence_url"]),
        ]
        if item["rights_review"].get("permission_record_url"):
            url_fields.append(("rights_review.permission_record_url",
                               item["rights_review"]["permission_record_url"]))
        for field, value in url_fields:
            if not _https_url(value) or re.search(r"\s", value):
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
        result = rights_status(item)
        if item["rights_review"]["status"] == "approved" and result != "approved":
            raise ValueError(f"{asset_id}: claimed approval lacks verifiable rights scope ({result})")
        counts["total"] += 1
        counts[result] += 1
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
