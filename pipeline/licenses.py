from __future__ import annotations

import re
from typing import Any


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def assess_license(provider: str, license_name: str) -> dict[str, Any]:
    provider_key = _norm(provider)
    name = _norm(license_name)

    if provider_key == "generated_fallback":
        return {"allowed": True, "requires_attribution": False, "reason": "Generated locally"}
    if provider_key == "pexels":
        return {
            "allowed": name == "pexels license",
            "requires_attribution": False,
            "reason": "Pexels License" if name == "pexels license" else "Unexpected Pexels license metadata",
        }

    forbidden = ("all rights reserved", "fair use", "noncommercial", "non-commercial", "-nc", "no derivatives", "-nd")
    if not name or any(token in name for token in forbidden):
        return {"allowed": False, "requires_attribution": False, "reason": "License is missing or incompatible with edited/public video use"}

    if "public domain" in name or name in {"cc0", "cc0 1.0"}:
        return {"allowed": True, "requires_attribution": False, "reason": "Public domain / CC0"}
    if "cc by-sa" in name or "creative commons attribution-share alike" in name or "creative commons attribution-sharealike" in name:
        return {"allowed": True, "requires_attribution": True, "reason": "CC BY-SA attribution/share-alike obligations"}
    if re.search(r"\bcc by(?: |$)", name) or "creative commons attribution" in name:
        return {"allowed": True, "requires_attribution": True, "reason": "CC BY attribution required"}
    return {"allowed": False, "requires_attribution": False, "reason": f"Unrecognized license: {license_name or 'missing'}"}
