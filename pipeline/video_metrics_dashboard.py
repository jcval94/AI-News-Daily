from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any


SCORE_SPECS = (
    ("editorial", "Editorial", "editorial"),
    ("attention", "Attention", "youtube_attention_master"),
    ("voice", "Voice", "voice_humanity"),
    ("seo", "SEO", "seo_master"),
)
COLORS = {
    "editorial": "#66d9ff",
    "attention": "#f7b267",
    "voice": "#9b8cff",
    "seo": "#63d3a6",
}


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
    return int(number) if number is not None else None


def _title(episode_dir: Path) -> str:
    plan = _read_json(episode_dir / "artifacts" / "episode_plan.json", {})
    if isinstance(plan, dict):
        for key in ("episode_title", "title", "topic", "angle", "thesis", "central_thesis"):
            value = plan.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:140]
    return "AI News Daily"


def _latest_script(episode_dir: Path) -> str:
    scripts = episode_dir / "scripts"
    if not scripts.exists():
        return ""
    paths = sorted(scripts.glob("latest-*.txt"), reverse=True)
    if not paths:
        return ""
    try:
        return paths[0].read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _is_video(item: dict[str, Any], rel: str) -> bool:
    asset_type = str(item.get("asset_type", "") or "").lower()
    mime_type = str(item.get("mime_type", "") or "").lower()
    return asset_type == "video" or mime_type.startswith("video/") or rel.lower().endswith(".mp4")


def _wall_seconds(state: dict[str, Any]) -> float | None:
    try:
        started = datetime.fromisoformat(str(state.get("started_at_utc")))
        finished = datetime.fromisoformat(str(state.get("finished_at_utc")))
        return max(0.0, (finished - started).total_seconds())
    except (TypeError, ValueError):
        return None


def _trace_metrics(trace: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    calls = trace.get("agent_calls") if isinstance(trace, dict) else None
    if not isinstance(calls, list):
        return None, None, None
    total_tokens = 0
    saw_tokens = False
    errors = 0
    attempts = 0
    for call in calls:
        if not isinstance(call, dict):
            continue
        attempts += 1
        if str(call.get("status", "") or "").lower() == "error":
            errors += 1
        usage = call.get("usage", {}) if isinstance(call.get("usage"), dict) else {}
        value = _as_int(usage.get("total_tokens"))
        if value is not None:
            total_tokens += value
            saw_tokens = True
    return (total_tokens if saw_tokens else None), attempts, errors


def episode_metrics(episode_dir: Path) -> dict[str, Any]:
    artifacts = episode_dir / "artifacts"
    reviews = _read_json(artifacts / "reviews.json", {})
    state = _read_json(artifacts / "run_state.json", {})
    novelty = _read_json(artifacts / "novelty_check.json", {})
    trace = _read_json(artifacts / "execution_trace.json", {})
    regression = _read_json(artifacts / "editorial-regression.json", {})
    manifest = _read_json(artifacts / "media-manifest.json", [])
    media_plan = _read_json(artifacts / "media-plan.json", {})
    cost_snapshot = _read_json(episode_dir / "downloads" / "cost_snapshot.json", {})

    reviews = reviews if isinstance(reviews, dict) else {}
    state = state if isinstance(state, dict) else {}
    scores: dict[str, float | None] = {}
    approvals: dict[str, bool | None] = {}
    for key, _, source_key in SCORE_SPECS:
        block = reviews.get(source_key, {}) if isinstance(reviews.get(source_key), dict) else {}
        scores[key] = _as_float(block.get("score"))
        approvals[key] = block.get("approved") if isinstance(block.get("approved"), bool) else None

    available_scores = [value for value in scores.values() if value is not None]
    average_score = round(sum(available_scores) / len(available_scores), 3) if available_scores else None

    gate = reviews.get("gate", {}) if isinstance(reviews.get("gate"), dict) else {}
    best = reviews.get("best_candidate", {}) if isinstance(reviews.get("best_candidate"), dict) else {}

    assets = 0
    videos = 0
    opening_assets = 0
    opening_videos = 0
    if isinstance(manifest, list):
        for raw in manifest:
            if not isinstance(raw, dict):
                continue
            rel = str(raw.get("file", "") or "").strip()
            if not rel:
                continue
            physical = episode_dir / "media" / rel
            if not physical.is_file():
                continue
            assets += 1
            is_video = _is_video(raw, rel)
            if is_video:
                videos += 1
            start = _as_float(raw.get("start_seconds"))
            if start is not None and start < 20:
                opening_assets += 1
                if is_video:
                    opening_videos += 1

    totals = cost_snapshot.get("totals", {}) if isinstance(cost_snapshot, dict) else {}
    cost = _as_float(totals.get("known_direct_cost_usd")) if isinstance(totals, dict) else None

    token_count, agent_attempts, agent_errors = _trace_metrics(trace if isinstance(trace, dict) else {})
    script = _latest_script(episode_dir)
    status = str(state.get("status") or "no_registrado")
    publishable = state.get("publishable") if isinstance(state.get("publishable"), bool) else None

    novelty_attempts = None
    if isinstance(novelty, dict) and isinstance(novelty.get("attempts"), list):
        novelty_attempts = len(novelty["attempts"])

    planned_opening_media = _as_int(media_plan.get("opening_media_count")) if isinstance(media_plan, dict) else None
    planned_opening_videos = _as_int(media_plan.get("opening_video_count")) if isinstance(media_plan, dict) else None

    return {
        "date": episode_dir.name,
        "title": _title(episode_dir),
        "status": status,
        "publishable": publishable,
        "scores": scores,
        "approvals": approvals,
        "average_score": average_score,
        "duration_seconds": _as_int(gate.get("duration_seconds")),
        "word_count": len(script.split()) if script else None,
        "asset_count": assets if isinstance(manifest, list) else None,
        "video_count": videos if isinstance(manifest, list) else None,
        "opening_asset_count": opening_assets if isinstance(manifest, list) else None,
        "opening_video_count": opening_videos if isinstance(manifest, list) else None,
        "planned_opening_media_count": planned_opening_media,
        "planned_opening_video_count": planned_opening_videos,
        "best_iteration": _as_int(best.get("iteration")),
        "judged_unique_script_count": _as_int(best.get("judged_unique_script_count")),
        "novelty_attempt_count": novelty_attempts,
        "structural_pass": regression.get("structural_pass") if isinstance(regression, dict) else None,
        "known_direct_cost_usd": cost,
        "recorded_total_tokens": token_count,
        "agent_attempt_count": agent_attempts,
        "agent_error_count": agent_errors,
        "wall_seconds": _wall_seconds(state),
    }


def discover_metrics(episodes_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not episodes_root.exists():
        return rows
    for episode_dir in episodes_root.iterdir():
        if episode_dir.is_dir() and (episode_dir / "index.html").is_file():
            rows.append(episode_metrics(episode_dir))
    rows.sort(key=lambda item: str(item.get("date") or ""))
    return rows


def _fmt(value: Any, decimals: int = 1) -> str:
    number = _as_float(value)
    return "—" if number is None else f"{number:.{decimals}f}"


def _fmt_int(value: Any) -> str:
    number = _as_int(value)
    return "—" if number is None else f"{number:,}"


def _fmt_duration(seconds: Any) -> str:
    number = _as_float(seconds)
    if number is None:
        return "—"
    return f"{number / 60.0:.1f} min"


def _fmt_wall(seconds: Any) -> str:
    number = _as_float(seconds)
    if number is None:
        return "—"
    minutes, secs = divmod(int(round(number)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _fmt_cost(value: Any) -> str:
    number = _as_float(value)
    return "—" if number is None else "$" + f"{number:.3f}"


def _avg(values: list[Any]) -> float | None:
    parsed = [number for value in values if (number := _as_float(value)) is not None]
    return sum(parsed) / len(parsed) if parsed else None


def _summary_card(key: str, label: str, rows: list[dict[str, Any]]) -> str:
    values = [row.get("scores", {}).get(key) for row in rows]
    avg = _avg(values)
    latest_values = [value for value in values if _as_float(value) is not None]
    latest = _as_float(latest_values[-1]) if latest_values else None
    previous = _as_float(latest_values[-2]) if len(latest_values) > 1 else None
    delta = latest - previous if latest is not None and previous is not None else None
    delta_text = "—" if delta is None else f"{delta:+.1f}"
    return (
        f'<article class="summary-card"><span>{html.escape(label)}</span>'
        f'<strong>{_fmt(latest)}</strong><small>último</small>'
        f'<div><b>{_fmt(avg)}</b> promedio · <b>{html.escape(delta_text)}</b> Δ vs previo</div></article>'
    )


def _score_cell(value: Any, approved: Any) -> str:
    klass = "pass" if approved is True else "fail" if approved is False else "neutral"
    return f'<span class="score-pill {klass}">{_fmt(value)}</span>'


def _score_chart(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="muted">No hay episodios con métricas todavía.</p>'
    width, height = 1100, 420
    left, right, top, bottom = 70, 30, 42, 76
    plot_w = width - left - right
    plot_h = height - top - bottom
    count = len(rows)

    def x_at(index: int) -> float:
        return left + (plot_w / 2 if count == 1 else (plot_w * index / (count - 1)))

    def y_at(score: float) -> float:
        bounded = max(0.0, min(10.0, score))
        return top + plot_h * (1.0 - bounded / 10.0)

    parts = [
        f'<svg class="trend-chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="score-chart-title score-chart-desc">',
        '<title id="score-chart-title">Histórico de Editorial, Attention, Voice y SEO</title>',
        '<desc id="score-chart-desc">Escala de cero a diez. Los puntos faltantes no se interpolan.</desc>',
    ]
    for tick in (0, 2, 4, 6, 8, 10):
        y = y_at(float(tick))
        parts.append(f'<line class="grid-line" x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis-label" x="{left-16}" y="{y+4:.1f}" text-anchor="end">{tick}</text>')

    for key, label, _ in SCORE_SPECS:
        previous: tuple[float, float] | None = None
        for index, row in enumerate(rows):
            score = _as_float(row.get("scores", {}).get(key))
            if score is None:
                previous = None
                continue
            x, y = x_at(index), y_at(score)
            if previous is not None:
                parts.append(
                    f'<line class="series-line" style="stroke:{COLORS[key]}" '
                    f'x1="{previous[0]:.1f}" y1="{previous[1]:.1f}" x2="{x:.1f}" y2="{y:.1f}"/>'
                )
            parts.append(
                f'<circle class="series-point" style="fill:{COLORS[key]}" cx="{x:.1f}" cy="{y:.1f}" r="5">'
                f'<title>{html.escape(label)} · {html.escape(str(row["date"]))} · {score:.1f}</title></circle>'
            )
            previous = (x, y)

    label_step = max(1, (count + 7) // 8)
    for index, row in enumerate(rows):
        if index % label_step != 0 and index != count - 1:
            continue
        x = x_at(index)
        parts.append(
            f'<text class="date-label" x="{x:.1f}" y="{height-34}" text-anchor="middle">'
            f'{html.escape(str(row["date"]))}</text>'
        )

    legend_x = left
    for key, label, _ in SCORE_SPECS:
        parts.append(f'<circle cx="{legend_x}" cy="20" r="5" style="fill:{COLORS[key]}"/>')
        parts.append(f'<text class="legend-label" x="{legend_x+10}" y="24">{html.escape(label)}</text>')
        legend_x += 150
    parts.append("</svg>")
    return "".join(parts)


def _table(rows: list[dict[str, Any]]) -> str:
    body: list[str] = []
    for row in reversed(rows):
        scores = row.get("scores", {})
        approvals = row.get("approvals", {})
        structural = row.get("structural_pass")
        structural_text = "PASS" if structural is True else "FAIL" if structural is False else "—"
        publishable = row.get("publishable")
        status_class = "pass" if publishable is True else "fail" if publishable is False else "neutral"
        body.append(
            '<tr data-metric-row>'
            f'<td class="sticky-col"><a target="_top" href="../?episode={html.escape(str(row["date"]), quote=True)}">{html.escape(str(row["date"]))}</a>'
            f'<small>{html.escape(str(row.get("title") or ""))}</small></td>'
            f'<td>{_score_cell(scores.get("editorial"), approvals.get("editorial"))}</td>'
            f'<td>{_score_cell(scores.get("attention"), approvals.get("attention"))}</td>'
            f'<td>{_score_cell(scores.get("voice"), approvals.get("voice"))}</td>'
            f'<td>{_score_cell(scores.get("seo"), approvals.get("seo"))}</td>'
            f'<td><strong>{_fmt(row.get("average_score"))}</strong></td>'
            f'<td><span class="status-pill {status_class}">{html.escape(str(row.get("status") or "—"))}</span></td>'
            f'<td>{_fmt_duration(row.get("duration_seconds"))}</td>'
            f'<td>{_fmt_int(row.get("word_count"))}</td>'
            f'<td>{_fmt_int(row.get("asset_count"))}</td>'
            f'<td>{_fmt_int(row.get("video_count"))}</td>'
            f'<td>{_fmt_int(row.get("opening_video_count"))}</td>'
            f'<td>{_fmt_int(row.get("judged_unique_script_count"))}</td>'
            f'<td>{_fmt_int(row.get("novelty_attempt_count"))}</td>'
            f'<td>{html.escape(structural_text)}</td>'
            f'<td>{_fmt_cost(row.get("known_direct_cost_usd"))}</td>'
            f'<td>{_fmt_int(row.get("recorded_total_tokens"))}</td>'
            f'<td>{_fmt_wall(row.get("wall_seconds"))}</td>'
            f'<td>{_fmt_int(row.get("agent_error_count"))}</td>'
            '</tr>'
        )
    return "".join(body)


def dashboard_document(rows: list[dict[str, Any]]) -> str:
    summary = "".join(_summary_card(key, label, rows) for key, label, _ in SCORE_SPECS)
    publishable_count = sum(1 for row in rows if row.get("publishable") is True)
    structural_count = sum(1 for row in rows if row.get("structural_pass") is True)
    avg_duration = _avg([row.get("duration_seconds") for row in rows])
    avg_cost = _avg([row.get("known_direct_cost_usd") for row in rows])
    chart = _score_chart(rows)
    table = _table(rows)
    coverage = sum(
        1 for row in rows
        if all(_as_float(row.get("scores", {}).get(key)) is not None for key, _, _ in SCORE_SPECS)
    )

    template = Template(r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Histórico de métricas · AI News Daily</title>
<style>
:root{--bg:#080d13;--panel:#101923;--panel2:#131f2b;--line:#26364a;--text:#eef6ff;--muted:#8da0b3;--accent:#66d9ff;--good:#63d3a6;--bad:#fb8294}
*{box-sizing:border-box}html{background:var(--bg)}body{margin:0;background:linear-gradient(180deg,#09111a,#080d13);color:var(--text);font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1440px;margin:auto;padding:32px 26px 70px}.eyebrow{text-transform:uppercase;letter-spacing:.13em;font-weight:850;font-size:10px;color:var(--accent)}
h1{font-size:clamp(30px,4vw,50px);line-height:1.05;margin:8px 0 10px}.lede{max-width:900px;color:#bfd0df;font-size:16px;margin:0}.note{margin-top:12px;color:var(--muted);font-size:12px}
.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:24px 0}.summary-card,.kpi{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:15px}.summary-card>span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.07em}.summary-card>strong{display:inline-block;font-size:31px;margin-top:5px}.summary-card>small{color:var(--muted);margin-left:6px}.summary-card>div{margin-top:7px;color:#b8c8d7;font-size:12px}
.kpi-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-bottom:20px}.kpi strong{display:block;font-size:20px}.kpi span{color:var(--muted);font-size:11px}
.section{margin-top:26px}.section-head{display:flex;gap:16px;align-items:end;justify-content:space-between}.section-head h2{margin:0;font-size:22px}.section-head p{margin:0;color:var(--muted);font-size:12px}
.chart-shell{margin-top:10px;border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:12px;overflow:auto}.trend-chart{display:block;min-width:780px;width:100%;height:auto}.grid-line{stroke:#27384b;stroke-width:1}.axis-label,.date-label,.legend-label{fill:#91a3b5;font-size:11px}.series-line{stroke-width:3;stroke-linecap:round}.series-point{stroke:#071019;stroke-width:2}
.table-toolbar{display:flex;gap:10px;align-items:center;margin:12px 0}.table-toolbar input{width:min(420px,100%);padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:#0a121b;color:var(--text)}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:15px;background:var(--panel)}table{border-collapse:collapse;width:100%;min-width:1680px}th,td{padding:10px;border-bottom:1px solid #223144;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#14202c;color:#a9bbcc;font-size:10px;text-transform:uppercase;letter-spacing:.05em;z-index:2}td{font-variant-numeric:tabular-nums}.sticky-col{position:sticky;left:0;background:#101923;z-index:1;min-width:220px}.sticky-col a{color:var(--accent);font-weight:800;text-decoration:none}.sticky-col small{display:block;color:var(--muted);max-width:250px;overflow:hidden;text-overflow:ellipsis}
.score-pill,.status-pill{display:inline-block;border-radius:999px;padding:4px 8px;font-weight:800}.pass{background:#16392f;color:#8be6c1}.fail{background:#41202a;color:#ffb3c0}.neutral{background:#243142;color:#c3d1de}
.muted{color:var(--muted)}.source-note{margin-top:12px;padding:13px;border:1px dashed #31465d;border-radius:12px;color:var(--muted);font-size:12px}
@media(max-width:900px){.summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.kpi-row{grid-template-columns:repeat(2,minmax(0,1fr))}.wrap{padding:22px 14px 60px}}@media(max-width:560px){.summary-grid,.kpi-row{grid-template-columns:1fr}.section-head{align-items:start;flex-direction:column}}
</style>
</head>
<body data-metrics-page="video-metrics-history">
<main class="wrap">
<span class="eyebrow">Histórico · calidad editorial</span>
<h1>Métricas de los episodios</h1>
<p class="lede">Evolución de Editorial, Attention, Voice y SEO a través de los episodios conservados en Pages, junto con señales de producción y costo útiles para detectar tendencias.</p>
<p class="note">Estas métricas provienen del pipeline editorial y sus artefactos persistidos; no son analytics posteriores de YouTube como views, CTR o retención.</p>

<div class="summary-grid">$summary</div>
<div class="kpi-row">
  <article class="kpi"><strong>$episode_count</strong><span>episodios en histórico</span></article>
  <article class="kpi"><strong>$coverage/$episode_count</strong><span>con los 4 scores</span></article>
  <article class="kpi"><strong>$publishable_count</strong><span>publicables registrados</span></article>
  <article class="kpi"><strong>$structural_count</strong><span>regression estructural PASS</span></article>
  <article class="kpi"><strong>$avg_duration</strong><span>duración promedio</span></article>
</div>

<section class="section">
  <div class="section-head"><div><span class="eyebrow">Tendencia principal</span><h2>Scores por episodio</h2></div><p>Escala 0–10 · faltantes no interpolados</p></div>
  <div class="chart-shell">$chart</div>
</section>

<section class="section">
  <div class="section-head"><div><span class="eyebrow">Detalle</span><h2>Histórico completo</h2></div><p>Costo promedio conocido: $avg_cost</p></div>
  <div class="table-toolbar"><input id="metricSearch" type="search" placeholder="Filtrar por fecha, título o estado…" aria-label="Filtrar histórico"></div>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Episodio</th><th>Editorial</th><th>Attention</th><th>Voice</th><th>SEO</th><th>Promedio</th><th>Estado</th><th>Duración</th><th>Palabras</th><th>Assets</th><th>Videos</th><th>Videos 0–20s</th><th>Guiones juzgados</th><th>Novelty</th><th>Regression</th><th>Costo</th><th>Tokens</th><th>Tiempo run</th><th>Errores agentes</th></tr></thead>
    <tbody>$table</tbody>
  </table>
  </div>
  <p class="source-note">Fuente: <code>reviews.json</code>, <code>run_state.json</code>, <code>editorial-regression.json</code>, <code>media-manifest.json</code>, <code>media-plan.json</code>, <code>novelty_check.json</code>, <code>execution_trace.json</code> y <code>cost_snapshot.json</code> de cada episodio recuperado. “—” significa que el artefacto histórico no conserva esa medición.</p>
</section>
</main>
<script>
const input=document.getElementById('metricSearch');
const rows=[...document.querySelectorAll('[data-metric-row]')];
if(input) input.addEventListener('input',()=>{
  const q=input.value.trim().toLocaleLowerCase('es');
  rows.forEach(row=>{row.hidden=Boolean(q)&&!row.textContent.toLocaleLowerCase('es').includes(q);});
});
</script>
</body>
</html>""")
    return template.substitute(
        summary=summary,
        episode_count=str(len(rows)),
        coverage=str(coverage),
        publishable_count=str(publishable_count),
        structural_count=str(structural_count),
        avg_duration=_fmt_duration(avg_duration),
        avg_cost=_fmt_cost(avg_cost),
        chart=chart,
        table=table,
    )


def build_dashboard(*, episodes_root: Path, output_dir: Path) -> Path:
    rows = discover_metrics(episodes_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "metric_scope": "editorial_pipeline_not_youtube_analytics",
        "episodes": rows,
    }
    (output_dir / "video-metrics-history.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    index_path = output_dir / "index.html"
    index_path.write_text(dashboard_document(rows), encoding="utf-8")
    return index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build historical editorial/video metrics dashboard")
    parser.add_argument("--episodes-root", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_dashboard(
        episodes_root=Path(args.episodes_root),
        output_dir=Path(args.output_dir),
    )
    print(result)


if __name__ == "__main__":
    main()
