from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import build_site as _build_site_v3
from pipeline.review_hub_v3 import parse_args


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


def _fmt_number(value: int | float | None, *, decimals: int = 0) -> str:
    if value is None:
        return "—"
    if decimals:
        return f"{float(value):,.{decimals}f}"
    return f"{int(value):,}"


def _fmt_elapsed(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _is_video(item: dict[str, Any], rel: str) -> bool:
    asset_type = str(item.get("asset_type", "") or "").lower()
    mime_type = str(item.get("mime_type", "") or "").lower()
    return asset_type == "video" or mime_type.startswith("video/") or rel.lower().endswith(".mp4")


def derive_real_indicators(
    *,
    episode_dir: Path,
    media_dir: Path,
    regression_path: Path,
    run_id: str,
) -> dict[str, Any]:
    """Derive displayed indicators only from persisted artifacts/files.

    Missing measurements remain missing. This function intentionally does not coerce absent
    values to zero and does not estimate monetary cost from current pricing.
    """

    script_path = episode_dir / "script.txt"
    script = script_path.read_text(encoding="utf-8").strip() if script_path.exists() else ""
    reviews = _read_json(episode_dir / "reviews.json", {})
    state = _read_json(episode_dir / "run_state.json", {})
    novelty = _read_json(episode_dir / "novelty_check.json", {})
    trace = _read_json(episode_dir / "execution_trace.json", {})
    regression = _read_json(regression_path, {})
    manifest = _read_json(media_dir / "manifest.json", [])

    manifest_items = manifest if isinstance(manifest, list) else []
    downloaded: list[dict[str, Any]] = []
    opening: list[dict[str, Any]] = []
    opening_videos: list[dict[str, Any]] = []
    for raw in manifest_items:
        if not isinstance(raw, dict):
            continue
        rel = str(raw.get("file", "") or "").strip()
        if not rel or not (media_dir / rel).is_file():
            continue
        downloaded.append(raw)
        start_seconds = _as_float(raw.get("start_seconds"))
        if start_seconds is not None and start_seconds < 20:
            opening.append(raw)
            if _is_video(raw, rel):
                opening_videos.append(raw)

    gate = reviews.get("gate", {}) if isinstance(reviews.get("gate"), dict) else {}
    editorial = reviews.get("editorial", {}) if isinstance(reviews.get("editorial"), dict) else {}
    seo = reviews.get("seo_master", {}) if isinstance(reviews.get("seo_master"), dict) else {}
    attention = reviews.get("youtube_attention_master", {}) if isinstance(reviews.get("youtube_attention_master"), dict) else {}
    voice = reviews.get("voice_humanity", {}) if isinstance(reviews.get("voice_humanity"), dict) else {}
    best = reviews.get("best_candidate", {}) if isinstance(reviews.get("best_candidate"), dict) else {}

    duration_seconds = _as_int(gate.get("duration_seconds"))
    scores = {
        "editorial": _as_float(editorial.get("score")),
        "seo": _as_float(seo.get("score")),
        "attention": _as_float(attention.get("score")),
        "voice": _as_float(voice.get("score")),
    }

    recorded_usage: dict[str, int] = {}
    agent_attempts = 0
    agent_errors = 0
    for call in trace.get("agent_calls", []) if isinstance(trace, dict) else []:
        if not isinstance(call, dict):
            continue
        agent_attempts += 1
        if str(call.get("status", "")).lower() == "error":
            agent_errors += 1
        usage = call.get("usage", {}) if isinstance(call.get("usage"), dict) else {}
        for key, value in usage.items():
            parsed = _as_int(value)
            if parsed is not None:
                recorded_usage[key] = recorded_usage.get(key, 0) + parsed

    wall_seconds: float | None = None
    try:
        started = datetime.fromisoformat(str(state.get("started_at_utc")))
        finished = datetime.fromisoformat(str(state.get("finished_at_utc")))
        wall_seconds = max(0.0, (finished - started).total_seconds())
    except (TypeError, ValueError):
        pass

    novelty_attempts = novelty.get("attempts", []) if isinstance(novelty, dict) else []
    if not isinstance(novelty_attempts, list):
        novelty_attempts = []

    return {
        "run_id": str(run_id),
        "episode_date": str(state.get("episode_date") or episode_dir.name),
        "status": str(state.get("status") or "pending"),
        "publishable": bool(state.get("publishable", False)),
        "word_count": len(script.split()) if script else None,
        "duration_seconds": duration_seconds,
        "duration_minutes": (duration_seconds / 60.0) if duration_seconds is not None else None,
        "asset_count": len(downloaded),
        "opening_asset_count": len(opening),
        "opening_video_count": len(opening_videos),
        "scores": scores,
        "best_iteration": _as_int(best.get("iteration")),
        "judged_unique_script_count": _as_int(best.get("judged_unique_script_count")),
        "novelty_attempt_count": len(novelty_attempts),
        "structural_pass": regression.get("structural_pass") if isinstance(regression, dict) else None,
        "recorded_total_tokens": recorded_usage.get("total_tokens"),
        "agent_attempt_count": agent_attempts,
        "agent_error_count": agent_errors,
        "wall_seconds": wall_seconds,
        "human_review_status": "pendiente",
    }


def _metric(value: str, label: str) -> str:
    return f'<div class="metric"><strong>{html.escape(value)}</strong><span>{html.escape(label)}</span></div>'


def apply_real_indicators(document: str, indicators: dict[str, Any]) -> str:
    status_text = "PUBLICABLE" if indicators["publishable"] else str(indicators["status"]).upper()
    status_class = "ok" if indicators["publishable"] else "bad"
    duration_minutes = indicators.get("duration_minutes")
    duration_label = (
        f"{float(duration_minutes):.1f} min estimados"
        if duration_minutes is not None
        else "duración no registrada"
    )

    hero_row_start = document.find('<div class="hero-row">')
    hero_row_end = document.find("</div>", hero_row_start)
    if hero_row_start < 0 or hero_row_end < 0:
        raise RuntimeError("Review Hub v4 could not find hero metrics row")
    hero_row_end += len("</div>")
    hero_row = (
        '<div class="hero-row">'
        f'<span class="badge {status_class}">{html.escape(status_text)}</span> '
        '<span class="muted">'
        f'{_fmt_number(indicators.get("word_count"))} palabras · {html.escape(duration_label)} · '
        f'{_fmt_number(indicators.get("asset_count"))} assets descargados · '
        f'{_fmt_number(indicators.get("opening_video_count"))} videos descargados en 0–20s'
        "</span></div>"
    )
    document = document[:hero_row_start] + hero_row + document[hero_row_end:]

    meta_start = document.find('<div class="hero-meta">')
    meta_end = document.find("</div>", meta_start)
    if meta_start < 0 or meta_end < 0:
        raise RuntimeError("Review Hub v4 could not find hero metadata")
    meta_end += len("</div>")
    validation_id = f'{indicators.get("episode_date")}-run-{indicators.get("run_id")}'
    hero_meta = (
        '<div class="hero-meta">'
        f'Revisión humana: <strong>{html.escape(str(indicators.get("human_review_status")))}</strong> · '
        f'fuente <code>{html.escape(validation_id)}</code> · '
        'indicadores derivados de artefactos persistidos, sin ceros sintéticos.'
        "</div>"
    )
    document = document[:meta_start] + hero_meta + document[meta_end:]

    metrics_start = document.find('<div class="metrics">')
    metrics_end_marker = '<div class="grid2">'
    metrics_end = document.find(metrics_end_marker, metrics_start)
    if metrics_start < 0 or metrics_end < 0:
        raise RuntimeError("Review Hub v4 could not find diagnostic metrics")

    scores = indicators.get("scores", {}) if isinstance(indicators.get("scores"), dict) else {}
    structural = indicators.get("structural_pass")
    structural_text = "PASS" if structural is True else "FAIL" if structural is False else "—"
    metrics_html = (
        '<div class="metrics">'
        + _metric(_fmt_number(scores.get("editorial"), decimals=1), "Editorial · reviews.json")
        + _metric(_fmt_number(scores.get("seo"), decimals=1), "SEO · reviews.json")
        + _metric(_fmt_number(scores.get("attention"), decimals=1), "Attention · reviews.json")
        + _metric(_fmt_number(scores.get("voice"), decimals=1), "Voice · reviews.json")
        + _metric(_fmt_number(indicators.get("asset_count")), "Assets descargados · manifest")
        + _metric(_fmt_number(indicators.get("opening_video_count")), "Videos 0–20s · manifest")
        + _metric(_fmt_number(indicators.get("judged_unique_script_count")), "Guiones juzgados")
        + _metric(_fmt_number(indicators.get("novelty_attempt_count")), "Intentos novelty")
        + _metric(structural_text, "Regression estructural")
        + _metric(_fmt_number(indicators.get("recorded_total_tokens")), "Tokens registrados")
        + _metric(_fmt_elapsed(indicators.get("wall_seconds")), "Tiempo run fuente")
        + _metric(_fmt_number(indicators.get("agent_error_count")), "Errores de agente registrados")
        + '</div>'
        + '<p class="muted metric-provenance">'
        + 'Procedencia: <code>run_state.json</code>, <code>reviews.json</code>, '
        + '<code>novelty_check.json</code>, <code>execution_trace.json</code>, '
        + '<code>editorial-regression.json</code> y archivos presentes en <code>media-manifest.json</code>. '
        + 'La duración es una estimación del gate, no tiempo de reproducción medido. '
        + 'El costo monetario no se muestra porque este run no persiste un snapshot de precios/costo; mostrar 0 o N/A como costo sería engañoso.'
        + '</p>'
    )
    document = document[:metrics_start] + metrics_html + document[metrics_end:]

    multimedia_heading = '<section id="multimedia" data-search-group><h2>Multimedia de revisión</h2>'
    multimedia_start = document.find(multimedia_heading)
    if multimedia_start >= 0:
        p_start = document.find("<p>", multimedia_start + len(multimedia_heading))
        p_end = document.find("</p>", p_start)
        if p_start >= 0 and p_end >= 0:
            p_end += len("</p>")
            multimedia_p = (
                '<p>Descargados realmente: '
                f'<strong>{_fmt_number(indicators.get("opening_asset_count"))}</strong> assets en 0–20s, '
                f'<strong>{_fmt_number(indicators.get("opening_video_count"))}</strong> videos en 0–20s; '
                f'total <strong>{_fmt_number(indicators.get("asset_count"))}</strong> assets presentes en el manifest y en disco.</p>'
            )
            document = document[:p_start] + multimedia_p + document[p_end:]

    return document


def build_site(
    *,
    episode_dir: Path,
    media_dir: Path,
    media_zip: Path,
    regression_path: Path,
    cases_path: Path,
    output_dir: Path,
    run_id: str,
) -> Path:
    index_path = _build_site_v3(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
    )
    indicators = derive_real_indicators(
        episode_dir=episode_dir,
        media_dir=media_dir,
        regression_path=regression_path,
        run_id=run_id,
    )
    document = apply_real_indicators(index_path.read_text(encoding="utf-8"), indicators)
    index_path.write_text(document, encoding="utf-8")
    return index_path


def main() -> None:
    args = parse_args()
    result = build_site(
        episode_dir=Path(args.episode_dir),
        media_dir=Path(args.media_dir),
        media_zip=Path(args.media_zip),
        regression_path=Path(args.regression),
        cases_path=Path(args.cases),
        output_dir=Path(args.output_dir),
        run_id=str(args.run_id),
    )
    print(result)


if __name__ == "__main__":
    main()
