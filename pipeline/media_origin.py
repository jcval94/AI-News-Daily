"""Deterministic source labels; these describe provenance, never relevance or rights."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

PROVIDERS = {
    "pexels": "Pexels", "commons": "Wikimedia Commons", "wikipedia": "Wikipedia",
    "archive": "Internet Archive", "youtube": "YouTube", "peertube": "PeerTube",
    "nasa": "NASA", "openverse": "Openverse", "met": "The Met",
    "aic": "Art Institute of Chicago", "loc": "Library of Congress",
    "generated_fallback": "Respaldo local", "unknown": "Sin fuente registrada",
}
ALIASES = {"wikimedia": "commons", "wikimedia_commons": "commons", "archive.org": "archive", "artic": "aic", "wikipedia": "commons"}
KINDS = {"external": "Externo", "local": "Local", "unknown": "Origen sin verificar"}
HOSTS = {"pexels.com": "pexels", "commons.wikimedia.org": "commons", "archive.org": "archive",
         "youtube.com": "youtube", "youtu.be": "youtube", "nasa.gov": "nasa"}


def source_origin(asset: dict[str, Any]) -> dict[str, Any]:
    """Derive from raw metadata, not a previous label; missing evidence stays unknown."""
    raw = str(asset.get("provider") or "").strip().lower()
    provider = ALIASES.get(raw, raw)
    basis = "provider" if raw else "unknown"
    if not provider:
        try:
            host = (urlsplit(str(asset.get("source_url") or "")).hostname or "").lower()
        except ValueError:
            host = ""
        provider = HOSTS.get(host.removeprefix("www."), "unknown")
        if provider != "unknown":
            basis = "source_url"
    kind = "local" if provider == "generated_fallback" else "external" if provider in PROVIDERS and provider != "unknown" else "unknown"
    provenance = asset.get("media_provenance")
    acquisition = "documentary_pool" if isinstance(provenance, dict) and provenance.get("source_asset_id") else "local_fallback" if kind == "local" else "standard" if provider in {"pexels", "commons"} else "unknown"
    return {"schema_version": 1, "provider": provider, "label": PROVIDERS.get(provider, provider),
            "kind": kind, "acquisition": acquisition, "basis": basis}


def label_manifest(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**asset, "source_origin": source_origin(asset)} for asset in manifest if isinstance(asset, dict)]
