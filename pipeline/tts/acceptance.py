from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audio_qa import inspect_wav
from .benchmark import benchmark_voices
from .config import DEFAULT_CONFIG, load_tts_config
from .engines import render_native, resolve_tts_python
from .release_store import promote_benchmark, promote_narration
from .render import _convert_edit, render_episode, resolve_episode


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _probe(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 30,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "output": ""}
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {
        "ok": proc.returncode == 0,
        "returncode": int(proc.returncode),
        "output": output[-1200:],
    }


def build_tts_doctor(
    *,
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path = Path("."),
    include_edge: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config = load_tts_config(config_path)
    tts = config["tts"]
    runtime = resolve_tts_python(config, repo_root)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, *, required: bool, detail: str) -> None:
        checks.append(
            {
                "name": name,
                "ok": bool(ok),
                "required": bool(required),
                "detail": detail,
            }
        )

    add(
        "tts_runtime",
        runtime.is_file(),
        required=True,
        detail=(
            str(runtime.relative_to(repo_root))
            if runtime.is_file()
            else str(runtime)
        ),
    )
    if runtime.is_file():
        result = _probe([str(runtime), "--version"], cwd=repo_root)
        add(
            "tts_python",
            bool(result["ok"]),
            required=True,
            detail=str(result.get("output") or result.get("error") or ""),
        )

    ffmpeg = shutil.which("ffmpeg")
    add("ffmpeg", bool(ffmpeg), required=True, detail=ffmpeg or "not found")
    ffprobe = shutil.which("ffprobe")
    add(
        "ffprobe",
        bool(ffprobe),
        required=False,
        detail=ffprobe or "not found",
    )
    gh = shutil.which("gh")
    add(
        "github_cli",
        bool(gh),
        required=False,
        detail=(gh or "not found") + " (required only for promote)",
    )
    espeak = shutil.which("espeak-ng")
    add(
        "espeak_ng",
        bool(espeak),
        required=False,
        detail=(
            espeak
            or "not found; verify Kokoro Spanish G2P if smoke fails"
        ),
    )

    primary = str(tts["engine"])
    fallback = tts.get("fallback", {})
    engines = [primary]
    if bool(fallback.get("enabled")):
        candidate = str(fallback.get("engine") or "")
        if candidate and candidate not in engines:
            engines.append(candidate)
    if include_edge and "edge" not in engines:
        engines.append("edge")

    module_by_engine = {
        "kokoro": "kokoro",
        "piper": "piper",
        "edge": "edge_tts",
    }
    if runtime.is_file():
        for engine in engines:
            module = module_by_engine[engine]
            result = _probe(
                [str(runtime), "-c", f"import {module}; print('ok')"],
                cwd=repo_root,
            )
            add(
                f"engine_import:{engine}",
                bool(result["ok"]),
                required=engine != "edge",
                detail=str(
                    result.get("output") or result.get("error") or ""
                ),
            )

    model_dir = repo_root / str(
        tts["engines"]
        .get("piper", {})
        .get("model_dir", ".local/models/piper")
    )
    piper_voice = str(
        tts["engines"].get("piper", {}).get("voice") or ""
    )
    piper_model = model_dir / f"{piper_voice}.onnx"
    piper_required = "piper" in engines
    add(
        "piper_model",
        piper_model.is_file(),
        required=piper_required,
        detail=(
            str(piper_model.relative_to(repo_root))
            if piper_model.is_file()
            else str(piper_model)
        ),
    )

    free_gb = shutil.disk_usage(repo_root).free / (1024 ** 3)
    add(
        "disk_free",
        free_gb >= 2.0,
        required=False,
        detail=f"{free_gb:.2f} GiB free",
    )

    failed_required = [
        item["name"]
        for item in checks
        if item["required"] and not item["ok"]
    ]
    warnings = [
        item["name"]
        for item in checks
        if not item["required"] and not item["ok"]
    ]
    status = "fail" if failed_required else ("warn" if warnings else "pass")
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "status": status,
        "required_failures": failed_required,
        "warnings": warnings,
        "checks": checks,
    }


def run_tts_smoke(
    *,
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path = Path("."),
    engine: str | None = None,
    include_edge: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    config = load_tts_config(config_path)
    tts = config["tts"]
    requested: list[str] = []
    if engine:
        requested.append(engine)
    else:
        requested.append(str(tts["engine"]))
        fallback = tts.get("fallback", {})
        fallback_engine = str(fallback.get("engine") or "")
        if (
            bool(fallback.get("enabled"))
            and fallback_engine
            and fallback_engine not in requested
        ):
            requested.append(fallback_engine)
    if include_edge and "edge" not in requested:
        requested.append("edge")

    text = (
        "OpenAI presentó una actualización. "
        "GPT-5 procesa 18.7 por ciento más rápido. "
        "Esta es una prueba breve de narración en español."
    )
    root = repo_root / ".local" / "tts" / "smoke"
    results: list[dict[str, Any]] = []
    for candidate in requested:
        voice = str(tts["engines"][candidate]["voice"])
        candidate_dir = root / candidate
        candidate_dir.mkdir(parents=True, exist_ok=True)
        text_path = candidate_dir / "smoke.txt"
        native = candidate_dir / "native.wav"
        edit = candidate_dir / "edit.wav"
        text_path.write_text(text + "\n", encoding="utf-8")
        try:
            meta = render_native(
                engine=candidate,
                voice=voice,
                text_file=text_path,
                output_file=native,
                config=config,
                repo_root=repo_root,
                timeout=180,
            )
            native_metrics = inspect_wav(native)
            _convert_edit(native, edit, int(tts["edit_sample_rate_hz"]))
            edit_metrics = inspect_wav(edit)
            results.append(
                {
                    "engine": candidate,
                    "voice": voice,
                    "status": "pass",
                    "generation_seconds": meta.get("generation_seconds"),
                    "native": native_metrics,
                    "edit": edit_metrics,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "engine": candidate,
                    "voice": voice,
                    "status": (
                        "fail" if candidate != "edge" else "warn"
                    ),
                    "error": str(exc),
                }
            )
    status = (
        "fail"
        if any(item["status"] == "fail" for item in results)
        else (
            "warn"
            if any(item["status"] == "warn" for item in results)
            else "pass"
        )
    )
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "status": status,
        "results": results,
    }


def _latest_manifest_for_script(
    script: str,
    *,
    repo_root: Path,
) -> Path:
    episode = resolve_episode(script, repo_root / "scripts")
    candidates = sorted(
        (repo_root / ".local" / "tts" / episode.name).glob(
            "*/narration_manifest.json"
        )
    )
    if not candidates:
        raise FileNotFoundError(
            f"No local TTS narration manifest found for "
            f"{episode.name}; render first"
        )
    return candidates[-1]


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_tts_acceptance(
    *,
    script: str = "latest",
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path = Path("."),
    include_edge: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "script": script,
    }
    doctor = build_tts_doctor(
        config_path=config_path,
        repo_root=repo_root,
        include_edge=include_edge,
    )
    report["doctor"] = doctor
    if doctor["status"] == "fail":
        report["status"] = "fail"
        report["stopped_after"] = "doctor"
        _write_report(
            repo_root / ".local/tts/acceptance.latest.json",
            report,
        )
        return report

    smoke = run_tts_smoke(
        config_path=config_path,
        repo_root=repo_root,
        include_edge=include_edge,
    )
    report["smoke"] = smoke
    if smoke["status"] == "fail":
        report["status"] = "fail"
        report["stopped_after"] = "smoke"
        _write_report(
            repo_root / ".local/tts/acceptance.latest.json",
            report,
        )
        return report

    episode = resolve_episode(script, repo_root / "scripts")
    manifest_path, manifest = render_episode(
        episode_dir=episode,
        config_path=config_path,
        repo_root=repo_root,
    )
    report["render"] = {
        "status": manifest["status"],
        "manifest": manifest_path.relative_to(repo_root).as_posix(),
        "engine": manifest["engine"],
        "duration_seconds": manifest["metrics"]["duration_seconds"],
        "qa": manifest["qa"]["status"],
    }

    benchmark_path = benchmark_voices(
        fixture=repo_root / "evals/tts/voice_bakeoff_es.txt",
        output_dir=repo_root / ".local/tts/benchmarks/latest",
        config_path=config_path,
        repo_root=repo_root,
    )
    benchmark_payload = json.loads(
        benchmark_path.read_text(encoding="utf-8")
    )
    report["benchmark"] = {
        "status": (
            "pass"
            if any(
                item.get("status") == "ok"
                for item in benchmark_payload.get("results", [])
            )
            else "fail"
        ),
        "path": benchmark_path.relative_to(repo_root).as_posix(),
        "candidates": benchmark_payload.get("results", []),
    }
    report["status"] = (
        "fail"
        if report["benchmark"]["status"] == "fail"
        else (
            "warn"
            if (
                smoke["status"] == "warn"
                or manifest["qa"]["status"] == "warn"
            )
            else "pass"
        )
    )
    _write_report(
        repo_root / ".local/tts/acceptance.latest.json",
        report,
    )
    return report


def run_local_tts_action(
    action: str,
    *,
    script: str = "latest",
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path = Path("."),
    engine: str | None = None,
    voice: str | None = None,
    include_edge: bool = False,
    push_contract: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if action == "doctor":
        return build_tts_doctor(
            config_path=config_path,
            repo_root=repo_root,
            include_edge=include_edge,
        )
    if action == "smoke":
        return run_tts_smoke(
            config_path=config_path,
            repo_root=repo_root,
            engine=engine,
            include_edge=include_edge,
        )
    if action == "render":
        episode = resolve_episode(script, repo_root / "scripts")
        path, payload = render_episode(
            episode_dir=episode,
            config_path=config_path,
            engine_override=engine,
            voice_override=voice,
            repo_root=repo_root,
        )
        return {
            "status": (
                "pass" if payload["status"] == "complete" else "fail"
            ),
            "manifest": path.relative_to(repo_root).as_posix(),
            "engine": payload["engine"],
            "duration_seconds": payload["metrics"]["duration_seconds"],
            "qa": payload["qa"],
        }
    if action == "benchmark":
        path = benchmark_voices(
            fixture=repo_root / "evals/tts/voice_bakeoff_es.txt",
            output_dir=repo_root / ".local/tts/benchmarks/latest",
            config_path=config_path,
            repo_root=repo_root,
        )
        return {
            "status": "pass",
            "benchmark": path.relative_to(repo_root).as_posix(),
        }
    if action == "accept":
        return run_tts_acceptance(
            script=script,
            config_path=config_path,
            repo_root=repo_root,
            include_edge=include_edge,
        )
    if action == "promote":
        manifest = _latest_manifest_for_script(
            script,
            repo_root=repo_root,
        )
        return promote_narration(
            manifest,
            config_path=config_path,
            repo_root=repo_root,
            push_contract=push_contract,
        )
    if action == "promote-benchmark":
        path = repo_root / ".local/tts/benchmarks/latest/benchmark.json"
        if not path.is_file():
            raise FileNotFoundError(
                "No latest TTS benchmark found; run benchmark first"
            )
        return promote_benchmark(
            path,
            script=script,
            config_path=config_path,
            repo_root=repo_root,
            push_contract=push_contract,
        )
    raise ValueError(f"Unknown local TTS action: {action}")
