from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import validate_manifest
from .render import _script_id, approved_episodes, render_episode


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _asset(run_dir: Path, relative: str) -> Path:
    root = run_dir.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Missing or unsafe narration asset: {relative}")
    return path


def _current_manifest(
    episode: Path,
    *,
    script_id: str,
    output_root: Path,
) -> tuple[Path, dict[str, Any]] | None:
    for path in sorted(
        (output_root / episode.name).glob("*/narration_manifest.json"),
        reverse=True,
    ):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate_manifest(payload)
            if payload["status"] != "complete" or payload["script_id"] != script_id:
                continue
            _asset(path.parent, payload["files"]["master_edit"])
            _asset(path.parent, payload["files"]["web_preview"])
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        return path, payload
    return None


def _repo_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _record(
    *,
    episode: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    result: str,
    repo_root: Path,
) -> dict[str, Any]:
    run_dir = manifest_path.parent
    preview = _asset(run_dir, manifest["files"]["web_preview"])
    master = _asset(run_dir, manifest["files"]["master_edit"])
    return {
        "episode_date": episode.name,
        "result": result,
        "script_id": manifest["script_id"],
        "manifest": _repo_path(manifest_path, repo_root),
        "preview": _repo_path(preview, repo_root),
        "master": _repo_path(master, repo_root),
        "engine": manifest["engine"]["used"],
        "voice": manifest["engine"]["voice"],
        "duration_seconds": manifest["metrics"]["duration_seconds"],
        "qa": manifest["qa"]["status"],
        "warnings": list(manifest["qa"].get("warnings") or []),
    }


def _relative_url(repo_path: str, *, catalog_dir: Path, repo_root: Path) -> str:
    return Path(os.path.relpath(repo_root / repo_path, catalog_dir)).as_posix()


def _write_catalog_html(path: Path, payload: dict[str, Any], repo_root: Path) -> None:
    cards: list[str] = []
    for item in reversed(payload["episodes"]):
        episode = html.escape(item["episode_date"])
        if item["result"] == "failed":
            cards.append(
                '<article class="failed">'
                f"<h2>{episode}</h2>"
                f"<p><strong>FAIL</strong> {html.escape(item['error'])}</p>"
                "</article>"
            )
            continue
        preview = html.escape(
            _relative_url(item["preview"], catalog_dir=path.parent, repo_root=repo_root),
            quote=True,
        )
        master = html.escape(
            _relative_url(item["master"], catalog_dir=path.parent, repo_root=repo_root),
            quote=True,
        )
        manifest = html.escape(
            _relative_url(item["manifest"], catalog_dir=path.parent, repo_root=repo_root),
            quote=True,
        )
        warnings = ""
        if item["warnings"]:
            warning_items = "".join(
                f"<li>{html.escape(str(value))}</li>" for value in item["warnings"]
            )
            warnings = f"<details><summary>Warnings</summary><ul>{warning_items}</ul></details>"
        cards.append(
            "<article>"
            f"<h2>{episode}</h2>"
            f"<audio controls preload=\"none\" src=\"{preview}\"></audio>"
            f"<p>{html.escape(item['engine'])} · {html.escape(item['voice'])} · "
            f"{float(item['duration_seconds']) / 60:.1f} min · QA {html.escape(item['qa'])}</p>"
            f'<p><a href="{preview}">MP3</a> · <a href="{master}">WAV 48 kHz</a> · '
            f'<a href="{manifest}">manifest</a></p>'
            f"{warnings}</article>"
        )
    document = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AI News Daily · Biblioteca TTS local</title>
<style>
body{{font:16px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;background:#101218;color:#eef}}
article{{background:#1a1e28;border:1px solid #343b4d;border-radius:12px;padding:1rem;margin:1rem 0}}
article.failed{{border-color:#b44}} audio{{width:100%}} a{{color:#8cc8ff}} h1,h2{{margin-top:0}}
</style></head><body><h1>Biblioteca TTS local</h1>
<p>Actualizada {html.escape(payload['generated_at_utc'])} · estado {html.escape(payload['status'])}</p>
{''.join(cards)}</body></html>
"""
    path.write_text(document, encoding="utf-8")


def render_pending_library(
    *,
    config_path: Path,
    repo_root: Path = Path("."),
    output_root: Path = Path(".local/tts"),
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    root = output_root if output_root.is_absolute() else repo_root / output_root
    library_dir = root / "library"
    episodes: list[dict[str, Any]] = []

    for episode in approved_episodes(repo_root / "scripts"):
        script_id = _script_id(episode)
        current = _current_manifest(episode, script_id=script_id, output_root=root)
        try:
            if current is None:
                manifest_path, manifest = render_episode(
                    episode_dir=episode,
                    config_path=config_path,
                    output_root=output_root,
                    repo_root=repo_root,
                )
                result = "rendered"
            else:
                manifest_path, manifest = current
                result = "current"
            episodes.append(
                _record(
                    episode=episode,
                    manifest_path=manifest_path,
                    manifest=manifest,
                    result=result,
                    repo_root=repo_root,
                )
            )
        except Exception as exc:
            episodes.append(
                {
                    "episode_date": episode.name,
                    "result": "failed",
                    "script_id": script_id,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    failed = any(item["result"] == "failed" for item in episodes)
    warned = any(item.get("qa") == "warn" for item in episodes)
    payload = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "status": "fail" if failed else ("warn" if warned else "pass"),
        "summary": {
            "approved": len(episodes),
            "rendered": sum(item["result"] == "rendered" for item in episodes),
            "current": sum(item["result"] == "current" for item in episodes),
            "failed": sum(item["result"] == "failed" for item in episodes),
        },
        "episodes": episodes,
        "listening_report": ".local/tts/library/index.html",
    }
    library_dir.mkdir(parents=True, exist_ok=True)
    (library_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_catalog_html(library_dir / "index.html", payload, repo_root)
    return payload
