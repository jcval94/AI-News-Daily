from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .config import DEFAULT_CONFIG, load_tts_config
from .contracts import validate_manifest
from .publish import (
    build_benchmark_web_manifest,
    build_web_manifest,
    write_benchmark_web_manifest,
    write_web_manifest,
)
from .render import _web_preview, resolve_episode


class ReleaseStoreError(RuntimeError):
    """Raised when the bounded GitHub Release store cannot complete an operation."""


def _run_gh(
    args: list[str],
    *,
    repo_root: Path,
    timeout: int = 180,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    gh = shutil.which("gh")
    if not gh:
        raise ReleaseStoreError("GitHub CLI (gh) is required for TTS promotion")
    proc = subprocess.run(
        [gh, *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )
    if check and proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-3000:]
        raise ReleaseStoreError(
            f"gh {' '.join(args[:3])} failed ({proc.returncode}): {tail}"
        )
    return proc


def resolve_repo_slug(repo_root: Path) -> str:
    proc = _run_gh(
        ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        repo_root=repo_root,
    )
    slug = proc.stdout.strip()
    if "/" not in slug:
        raise ReleaseStoreError(f"Could not resolve GitHub repository slug: {slug!r}")
    return slug


def _ensure_release(
    *,
    tag: str,
    title: str,
    notes: str,
    repo_slug: str,
    target_branch: str,
    repo_root: Path,
) -> None:
    exists = _run_gh(
        ["release", "view", tag, "--repo", repo_slug],
        repo_root=repo_root,
        check=False,
    )
    if exists.returncode == 0:
        return
    _run_gh(
        [
            "release",
            "create",
            tag,
            "--repo",
            repo_slug,
            "--target",
            target_branch,
            "--title",
            title,
            "--notes",
            notes,
        ],
        repo_root=repo_root,
    )


def _replace_release(
    *,
    tag: str,
    title: str,
    notes: str,
    repo_slug: str,
    target_branch: str,
    repo_root: Path,
) -> None:
    exists = _run_gh(
        ["release", "view", tag, "--repo", repo_slug],
        repo_root=repo_root,
        check=False,
    )
    if exists.returncode == 0:
        _run_gh(
            [
                "release",
                "delete",
                tag,
                "--repo",
                repo_slug,
                "--cleanup-tag",
                "--yes",
            ],
            repo_root=repo_root,
        )
    _ensure_release(
        tag=tag,
        title=title,
        notes=notes,
        repo_slug=repo_slug,
        target_branch=target_branch,
        repo_root=repo_root,
    )


def _asset_url(repo_slug: str, tag: str, path: Path) -> str:
    return (
        f"https://github.com/{repo_slug}/releases/download/"
        f"{quote(tag, safe='')}/{quote(path.name, safe='')}"
    )


def _upload_assets(
    *,
    tag: str,
    repo_slug: str,
    assets: list[Path],
    repo_root: Path,
) -> None:
    missing = [str(path) for path in assets if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing TTS web assets: " + ", ".join(missing))
    if not assets:
        raise ReleaseStoreError("No TTS assets were supplied for upload")
    _run_gh(
        [
            "release",
            "upload",
            tag,
            *[str(path) for path in assets],
            "--clobber",
            "--repo",
            repo_slug,
        ],
        repo_root=repo_root,
        timeout=600,
    )


def preview_release_tags_to_delete(
    releases: list[dict[str, Any]],
    *,
    prefix: str,
    keep: int,
    current_tag: str,
) -> list[str]:
    if keep < 1:
        raise ValueError("keep must be >= 1")
    candidates = [
        item
        for item in releases
        if str(item.get("tagName") or "").startswith(prefix)
    ]
    candidates.sort(
        key=lambda item: str(item.get("createdAt") or ""),
        reverse=True,
    )
    protected: set[str] = {current_tag}
    for item in candidates:
        tag = str(item.get("tagName") or "")
        if not tag or tag in protected:
            continue
        if len(protected) >= keep:
            break
        protected.add(tag)
    return [
        str(item.get("tagName"))
        for item in candidates
        if str(item.get("tagName") or "") not in protected
    ]


def _garbage_collect_preview_releases(
    *,
    repo_slug: str,
    prefix: str,
    keep: int,
    current_tag: str,
    repo_root: Path,
) -> list[str]:
    proc = _run_gh(
        [
            "release",
            "list",
            "--repo",
            repo_slug,
            "--limit",
            "100",
            "--json",
            "tagName,createdAt",
        ],
        repo_root=repo_root,
    )
    payload = json.loads(proc.stdout or "[]")
    if not isinstance(payload, list):
        raise ReleaseStoreError("gh release list did not return a JSON list")
    deleted = preview_release_tags_to_delete(
        payload,
        prefix=prefix,
        keep=keep,
        current_tag=current_tag,
    )
    for tag in deleted:
        _run_gh(
            [
                "release",
                "delete",
                tag,
                "--repo",
                repo_slug,
                "--cleanup-tag",
                "--yes",
            ],
            repo_root=repo_root,
        )
    return deleted


def _push_contract_file(
    path: Path,
    *,
    repo_slug: str,
    branch: str,
    repo_root: Path,
    message: str,
) -> None:
    relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
    lookup = _run_gh(
        [
            "api",
            f"repos/{repo_slug}/contents/{relative}?ref={branch}",
            "--jq",
            ".sha",
        ],
        repo_root=repo_root,
        check=False,
    )
    sha = lookup.stdout.strip() if lookup.returncode == 0 else ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    args = [
        "api",
        f"repos/{repo_slug}/contents/{relative}",
        "--method",
        "PUT",
        "-f",
        f"message={message}",
        "-f",
        f"content={encoded}",
        "-f",
        f"branch={branch}",
    ]
    if sha:
        args.extend(["-f", f"sha={sha}"])
    _run_gh(args, repo_root=repo_root)


def promote_narration(
    manifest_path: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path = Path("."),
    push_contract: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    config = load_tts_config(config_path)
    tts = config["tts"]
    release_cfg = tts.get("web", {}).get("release", {})
    prefix = str(release_cfg.get("preview_prefix", "tts-preview-"))
    branch = str(release_cfg.get("target_branch", "main"))
    keep = int(tts.get("retention", {}).get("pages_episode_audio_limit", 3))
    repo_slug = resolve_repo_slug(repo_root)
    tag = f"{prefix}{manifest['episode_date']}-{manifest['run_id']}"

    run_dir = manifest_path.parent
    master = run_dir / str(manifest["files"]["web_preview"])
    section_paths: dict[str, Path] = {}
    for item in manifest["sections"]:
        web_file = item.get("audio_web_file")
        if not web_file:
            raise ReleaseStoreError(
                f"Manifest section {item['id']!r} has no audio_web_file"
            )
        section_paths[str(item["id"])] = run_dir / str(web_file)

    _ensure_release(
        tag=tag,
        title=f"TTS preview · {manifest['episode_date']}",
        notes=(
            "Bounded AI-News-Daily TTS preview assets. "
            "High-quality WAV files remain local and are never committed."
        ),
        repo_slug=repo_slug,
        target_branch=branch,
        repo_root=repo_root,
    )
    assets = [master, *section_paths.values()]
    _upload_assets(
        tag=tag,
        repo_slug=repo_slug,
        assets=assets,
        repo_root=repo_root,
    )

    master_url = _asset_url(repo_slug, tag, master)
    section_urls = {
        section_id: _asset_url(repo_slug, tag, path)
        for section_id, path in section_paths.items()
    }
    web_manifest = build_web_manifest(
        manifest,
        master_url=master_url,
        section_urls=section_urls,
    )
    contract_path = (
        repo_root
        / "scripts"
        / str(manifest["episode_date"])
        / "tts"
        / "narration_web.json"
    )
    write_web_manifest(contract_path, web_manifest)

    deleted = _garbage_collect_preview_releases(
        repo_slug=repo_slug,
        prefix=prefix,
        keep=keep,
        current_tag=tag,
        repo_root=repo_root,
    )
    if push_contract:
        _push_contract_file(
            contract_path,
            repo_slug=repo_slug,
            branch=branch,
            repo_root=repo_root,
            message=f"tts: publish narration preview for {manifest['episode_date']}",
        )
    return {
        "status": "success",
        "release_tag": tag,
        "master_preview_url": master_url,
        "contract": contract_path.relative_to(repo_root).as_posix(),
        "deleted_release_tags": deleted,
        "contract_pushed": bool(push_contract),
    }


def promote_benchmark(
    benchmark_path: Path,
    *,
    script: str = "latest",
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path = Path("."),
    push_contract: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    benchmark_path = benchmark_path.resolve()
    report = json.loads(benchmark_path.read_text(encoding="utf-8"))
    common_text = (
        benchmark_path.parent / "benchmark_text.txt"
    ).read_text(encoding="utf-8")
    config = load_tts_config(config_path)
    tts = config["tts"]
    release_cfg = tts.get("web", {}).get("release", {})
    tag = str(release_cfg.get("benchmark_tag", "tts-benchmark-latest"))
    branch = str(release_cfg.get("target_branch", "main"))
    bitrate = str(tts.get("web", {}).get("bitrate", "64k"))
    repo_slug = resolve_repo_slug(repo_root)

    web_dir = benchmark_path.parent / "web"
    preview_paths: dict[str, Path] = {}
    for item in report.get("results", []):
        if (
            not isinstance(item, dict)
            or item.get("status") != "ok"
            or not item.get("edit_file")
        ):
            continue
        engine = str(item.get("engine") or "")
        voice = str(item.get("voice") or "")
        key = f"{engine}::{voice}"
        edit = benchmark_path.parent / str(item["edit_file"])
        output = (web_dir / f"{engine}__{voice}".replace("/", "-")).with_suffix(
            ".mp3"
        )
        _web_preview(edit, output, bitrate)
        preview_paths[key] = output

    _replace_release(
        tag=tag,
        title="TTS voice bake-off · latest",
        notes=(
            "Rolling AI-News-Daily TTS bake-off previews. "
            "The release is replaced on promotion so stale assets cannot accumulate."
        ),
        repo_slug=repo_slug,
        target_branch=branch,
        repo_root=repo_root,
    )
    _upload_assets(
        tag=tag,
        repo_slug=repo_slug,
        assets=list(preview_paths.values()),
        repo_root=repo_root,
    )
    preview_urls = {
        key: _asset_url(repo_slug, tag, path)
        for key, path in preview_paths.items()
    }
    episode = resolve_episode(script, repo_root / "scripts")
    web_manifest = build_benchmark_web_manifest(
        report,
        common_text=common_text,
        preview_urls=preview_urls,
    )
    contract_path = episode / "tts" / "benchmark_web.json"
    write_benchmark_web_manifest(contract_path, web_manifest)
    if push_contract:
        _push_contract_file(
            contract_path,
            repo_slug=repo_slug,
            branch=branch,
            repo_root=repo_root,
            message=f"tts: publish voice bake-off for {episode.name}",
        )
    return {
        "status": "success",
        "release_tag": tag,
        "contract": contract_path.relative_to(repo_root).as_posix(),
        "candidate_count": len(preview_urls),
        "contract_pushed": bool(push_contract),
    }
