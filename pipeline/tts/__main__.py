from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import benchmark_voices
from .config import DEFAULT_CONFIG
from .contracts import validate_manifest
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
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    validate_manifest(payload)
    print(json.dumps({"valid": True, "manifest": args.manifest}, indent=2))


if __name__ == "__main__":
    main()
