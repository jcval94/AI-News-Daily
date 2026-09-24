from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalized_source_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.lower()
    if not parts.scheme or not parts.netloc:
        return raw.lower()
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            "",
            "",
        )
    )


def _file_path(root: Path, item: dict[str, Any]) -> Path | None:
    relative = str(item.get("file", "") or "").strip()
    if not relative:
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def _file_sha256(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_identity_keys(item: dict[str, Any], *, media_root: Path) -> list[str]:
    """Return stable duplicate keys from strongest to weakest.

    Provider IDs catch the same upstream asset even when different rendition URLs were
    downloaded. Source URLs catch older manifests without IDs. File hashes catch exact
    local duplicates such as deterministic fallback cards.
    """
    keys: list[str] = []
    provider = str(item.get("provider", "") or "").strip().lower()
    provider_asset_id = str(item.get("provider_asset_id", "") or "").strip()
    if provider and provider_asset_id:
        keys.append(f"provider:{provider}:{provider_asset_id}")

    source_url = _normalized_source_url(item.get("source_url"))
    if source_url:
        keys.append(f"source:{source_url}")

    # Avoid hashing large videos/images when the provider already gives us a stable
    # identity. Hashing is a fallback for local/legacy assets with no upstream key.
    if keys:
        return keys

    digest = _file_sha256(_file_path(media_root, item))
    if digest:
        keys.append(f"sha256:{digest}")
    return keys


def resolution_rank(item: dict[str, Any], *, media_root: Path) -> tuple[int, int, int, int]:
    """Rank duplicate renditions with resolution as the absolute first criterion."""
    width = _int(item.get("source_width") or item.get("width"))
    height = _int(item.get("source_height") or item.get("height"))
    pixels = width * height
    path = _file_path(media_root, item)
    try:
        file_size = path.stat().st_size if path and path.is_file() else 0
    except OSError:
        file_size = 0
    return pixels, min(width, height), max(width, height), file_size


def deduplicate_materialized_media(
    manifest: list[dict[str, Any]],
    selected_segments: list[dict[str, Any]],
    *,
    media_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove repeated assets and keep the highest-resolution rendition.

    Duplicate identity is based on provider asset ID, normalized source URL, or exact
    file content. If duplicates differ in rendition quality, source resolution wins
    before file size. Loser files are deleted so the Review Hub and ZIP cannot surface
    them accidentally.
    """
    if len(manifest) < 2:
        return manifest, selected_segments, []

    # Build connected groups because an older item may match by URL while a newer item
    # also introduces the provider ID for the same resource.
    parent = list(range(len(manifest)))
    seen: dict[str, int] = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for index, item in enumerate(manifest):
        if not isinstance(item, dict):
            continue
        for key in asset_identity_keys(item, media_root=media_root):
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index

    groups: dict[int, list[int]] = {}
    for index in range(len(manifest)):
        groups.setdefault(find(index), []).append(index)

    keep_indices: set[int] = set()
    removed: list[dict[str, Any]] = []
    for indices in groups.values():
        if len(indices) == 1:
            keep_indices.add(indices[0])
            continue

        winner = max(
            indices,
            key=lambda idx: (
                resolution_rank(manifest[idx], media_root=media_root),
                -float(manifest[idx].get("start_seconds", 0) or 0),
                -_int(manifest[idx].get("shot_number")),
            ),
        )
        keep_indices.add(winner)
        winner_item = manifest[winner]
        winner_rank = resolution_rank(winner_item, media_root=media_root)
        for idx in indices:
            if idx == winner:
                continue
            loser = manifest[idx]
            loser_rank = resolution_rank(loser, media_root=media_root)
            loser_path = _file_path(media_root, loser)
            winner_path = _file_path(media_root, winner_item)
            if loser_path and loser_path != winner_path and loser_path.is_file():
                try:
                    loser_path.unlink()
                except OSError:
                    pass
            removed.append(
                {
                    "removed_shot_number": _int(loser.get("shot_number")),
                    "kept_shot_number": _int(winner_item.get("shot_number")),
                    "provider": str(loser.get("provider", "") or ""),
                    "provider_asset_id": str(loser.get("provider_asset_id", "") or ""),
                    "source_url": str(loser.get("source_url", "") or ""),
                    "removed_resolution": [loser_rank[1], loser_rank[2]],
                    "kept_resolution": [winner_rank[1], winner_rank[2]],
                    "reason": "duplicate_asset_lower_or_equal_resolution",
                }
            )

    deduped_manifest = [
        item for index, item in enumerate(manifest) if index in keep_indices
    ]
    kept_shots = {
        _int(item.get("shot_number"))
        for item in deduped_manifest
        if isinstance(item, dict) and _int(item.get("shot_number")) > 0
    }
    deduped_segments = [
        item
        for item in selected_segments
        if _int(item.get("slot_number")) in kept_shots
    ]
    return deduped_manifest, deduped_segments, removed
