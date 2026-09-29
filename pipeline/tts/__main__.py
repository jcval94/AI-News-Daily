from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import benchmark_voices
from .config import DEFAULT_CONFIG
from .contracts import validate_manifest
from .publish import (
    build_benchmark_web_manifest,
    build_web_manifest,
    read_url_map,
    write_benchmark_web_manifest,
    write_web_manifest,
)
from .render import render_episode, resolve_episode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m pipeline.tts", description="AI News Daily local-first TTS")
    sub = parser.add_subparsers(dest="command", required=True)
    render = sub.add_parser("render", help="Render one approved script by semantic section")
    render.add_argument("--script", default="latest")
    render.add_argument("--engine", choices=("kokoro", "piper", "edge"))
    render.add_argument("--voice")
    render.add_argument("--config", default=str(DEFAULT_CONFIG))
    render.add_argument("--output-root", default=".local/tts")

    benchmark = sub.add_parser("benchmark", help="Run the reproducible voice bake-off")
    benchmark.add_argument("--fixture", default="evals/tts/voice_bakeoff_es.txt")
    benchmark.add_argument("--output-dir", default=".local/tts/benchmarks/latest")
    benchmark.add_argument("--config", default=str(DEFAULT_CONFIG))

    validate = sub.add_parser("validate", help="Validate a narration manifest contract")
    validate.add_argument("manifest")

    publish = sub.add_parser("publish-web", help="Write the small Pages narration contract from already-hosted preview URLs")
    publish.add_argument("--manifest", required=True)
    publish.add_argument("--master-url", required=True)
    publish.add_argument("--section-urls-json")
    publish.add_argument("--output")

    publish_benchmark = sub.add_parser("publish-benchmark", help="Write the small Pages bake-off contract from already-hosted preview URLs")
    publish_benchmark.add_argument("--benchmark", default=".local/tts/benchmarks/latest/benchmark.json")
    publish_benchmark.add_argument("--preview-urls-json", required=True)
    publish_benchmark.add_argument("--script", default="latest")
    publish_benchmark.add_argument("--output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path.cwd().resolve()
    if args.command == "render":
        episode = resolve_episode(args.script, repo_root / "scripts")
        path, payload = render_episode(
            episode_dir=episode,
            config_path=repo_root / args.config,
            engine_override=args.engine,
            voice_override=args.voice,
            output_root=Path(args.output_root),
            repo_root=repo_root,
        )
        print(json.dumps({
            "manifest": str(path.relative_to(repo_root)), "status": payload["status"],
            "engine": payload["engine"], "duration_seconds": payload["metrics"]["duration_seconds"]
        }, ensure_ascii=False, indent=2))
        return
    if args.command == "benchmark":
        path = benchmark_voices(
            fixture=repo_root / args.fixture,
            output_dir=repo_root / args.output_dir,
            config_path=repo_root / args.config,
            repo_root=repo_root,
        )
        print(json.dumps({"benchmark": str(path.relative_to(repo_root))}, indent=2))
        return
    if args.command == "publish-web":
        manifest_path = (repo_root / args.manifest).resolve()
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_manifest(payload)
        section_urls = read_url_map((repo_root / args.section_urls_json).resolve() if args.section_urls_json else None)
        web = build_web_manifest(payload, master_url=args.master_url, section_urls=section_urls)
        output = (
            (repo_root / args.output).resolve()
            if args.output
            else repo_root / "scripts" / str(payload["episode_date"]) / "tts" / "narration_web.json"
        )
        write_web_manifest(output, web)
        print(json.dumps({"web_manifest": str(output.relative_to(repo_root)), "available": web["available"]}, indent=2))
        return
    if args.command == "publish-benchmark":
        benchmark_path = (repo_root / args.benchmark).resolve()
        report = json.loads(benchmark_path.read_text(encoding="utf-8"))
        common_text_path = benchmark_path.parent / "benchmark_text.txt"
        common_text = common_text_path.read_text(encoding="utf-8")
        preview_urls = read_url_map((repo_root / args.preview_urls_json).resolve())
        episode = resolve_episode(args.script, repo_root / "scripts")
        web = build_benchmark_web_manifest(report, common_text=common_text, preview_urls=preview_urls)
        output = (
            (repo_root / args.output).resolve()
            if args.output
            else episode / "tts" / "benchmark_web.json"
        )
        write_benchmark_web_manifest(output, web)
        print(json.dumps({"benchmark_web_manifest": str(output.relative_to(repo_root)), "available": web["available"]}, indent=2))
        return
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    validate_manifest(payload)
    print(json.dumps({"valid": True, "manifest": args.manifest}, indent=2))


if __name__ == "__main__":
    main()
