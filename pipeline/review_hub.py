from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any

from pipeline.core import PipelineConfig

CONFIG = PipelineConfig.from_env()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def bool_badge(value: Any, *, true_text: str = "PASS", false_text: str = "FAIL") -> str:
    ok = bool(value)
    klass = "ok" if ok else "bad"
    return f'<span class="badge {klass}">{true_text if ok else false_text}</span>'


def copy_file(source: Path, destination: Path) -> bool:
    if not source.exists() or not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def problems_block(label: str, review: dict[str, Any]) -> str:
    items = list(review.get("problems", []) or []) + list(review.get("improvements", []) or [])
    if not items:
        return ""
    lis = "".join(f"<li>{esc(item)}</li>" for item in items[:8])
    return f"<div class='review-notes'><h4>{esc(label)}</h4><ul>{lis}</ul></div>"


def historical_scripts(cases_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    payload = read_json(cases_path, {})
    rows: list[dict[str, Any]] = []
    repo_root = cases_path.parents[2] if len(cases_path.parents) >= 3 else Path(".")
    for case in payload.get("cases", []) if isinstance(payload, dict) else []:
        if not isinstance(case, dict):
            continue
        script_path = repo_root / str(case.get("script_path", ""))
        case_id = str(case.get("case_id", "") or script_path.parent.name)
        target = output_dir / "scripts" / f"{case_id}.txt"
        copied = copy_file(script_path, target)
        human = case.get("human", {}) if isinstance(case.get("human"), dict) else {}
        rows.append(
            {
                "case_id": case_id,
                "run_id": case.get("workflow_run_id"),
                "publishable": human.get("publishable"),
                "positive_signals": human.get("positive_signals", []),
                "rejection_reasons": human.get("rejection_reasons", []),
                "href": f"scripts/{target.name}" if copied else "",
            }
        )
    return rows


def _render_media_preview(item: dict[str, Any], rel: str) -> str:
    asset_type = str(item.get("asset_type", "") or "").lower()
    mime_type = str(item.get("mime_type", "") or "").lower()
    href = f"media/{esc(rel)}"
    label = esc(item.get("on_screen_text") or item.get("visual_query"))
    if asset_type == "video" or mime_type.startswith("video/") or rel.lower().endswith(".mp4"):
        return (
            f"<video controls muted loop playsinline preload='metadata' title='{label}'>"
            f"<source src='{href}' type='{esc(mime_type or 'video/mp4')}'>"
            "Tu navegador no soporta video HTML5."
            "</video>"
        )
    return f"<a href='{href}' target='_blank'><img src='{href}' loading='lazy' alt='{label}'></a>"


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
    output_dir.mkdir(parents=True, exist_ok=True)
    script = (episode_dir / "script.txt").read_text(encoding="utf-8").strip()
    plan = read_json(episode_dir / "episode_plan.json", {})
    sections = read_json(episode_dir / "script_sections.json", {})
    reviews = read_json(episode_dir / "reviews.json", {})
    state = read_json(episode_dir / "run_state.json", {})
    selected = read_json(episode_dir / "selected_news.json", {})
    novelty = read_json(episode_dir / "novelty_check.json", {})
    regression = read_json(regression_path, {})
    manifest = read_json(media_dir / "manifest.json", [])
    media_plan = read_json(media_dir / "plan.json", {})

    target_date = str(state.get("episode_date", episode_dir.name))
    validation_id = f"{target_date}-run-{run_id}"
    words = len(script.split())
    duration_seconds = int((reviews.get("gate", {}) or {}).get("duration_seconds", 0) or round(words / CONFIG.words_per_second))
    minutes = duration_seconds / 60.0
    opening_media_count = int(media_plan.get("opening_media_count", 0) or 0) if isinstance(media_plan, dict) else 0
    opening_video_count = int(media_plan.get("opening_video_count", 0) or 0) if isinstance(media_plan, dict) else 0

    copy_file(episode_dir / "script.txt", output_dir / "scripts" / f"latest-{validation_id}.txt")
    for name in (
        "episode_plan.json",
        "script_sections.json",
        "reviews.json",
        "run_state.json",
        "selected_news.json",
        "novelty_check.json",
        "execution_trace.json",
    ):
        copy_file(episode_dir / name, output_dir / "artifacts" / name)
    copy_file(regression_path, output_dir / "artifacts" / "editorial-regression.json")
    copy_file(media_dir / "manifest.json", output_dir / "artifacts" / "media-manifest.json")
    copy_file(media_dir / "plan.json", output_dir / "artifacts" / "media-plan.json")
    copy_file(media_dir / "credits.md", output_dir / "artifacts" / "credits.md")
    media_zip_name = media_zip.name
    copy_file(media_zip, output_dir / "downloads" / media_zip_name)

    for item in manifest if isinstance(manifest, list) else []:
        rel = str(item.get("file", "") or "")
        if rel:
            copy_file(media_dir / rel, output_dir / "media" / rel)

    history = historical_scripts(cases_path, output_dir)
    editorial = reviews.get("editorial", {}) if isinstance(reviews.get("editorial"), dict) else {}
    seo = reviews.get("seo_master", {}) if isinstance(reviews.get("seo_master"), dict) else {}
    attention = reviews.get("youtube_attention_master", {}) if isinstance(reviews.get("youtube_attention_master"), dict) else {}
    voice = reviews.get("voice_humanity", {}) if isinstance(reviews.get("voice_humanity"), dict) else {}
    best = reviews.get("best_candidate", {}) if isinstance(reviews.get("best_candidate"), dict) else {}
    arc = plan.get("narrative_arc", {}) if isinstance(plan.get("narrative_arc"), dict) else {}

    beat_rows = []
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in plan.get("evidence", []) if isinstance(item, dict)
    }
    selected_items = selected.get("items", []) if isinstance(selected, dict) else []
    for index, beat in enumerate(plan.get("beats", []) if isinstance(plan, dict) else [], start=1):
        if not isinstance(beat, dict):
            continue
        evidence_html = []
        for evidence_id in beat.get("evidence_ids", []) or []:
            evidence = evidence_by_id.get(str(evidence_id), {})
            selected_index = int(evidence.get("selected_news_index", 0) or 0)
            title = ""
            if 1 <= selected_index <= len(selected_items) and isinstance(selected_items[selected_index - 1], dict):
                title = str(selected_items[selected_index - 1].get("title", "") or "")
            evidence_html.append(f"<span class='evidence'>{esc(evidence_id)}{': ' + esc(title) if title else ''}</span>")
        beat_rows.append(
            f"<article class='beat'><div class='beat-no'>{index:02d}</div><div><h3>{esc(beat.get('beat_id'))}</h3>"
            f"<p class='muted'>{esc(beat.get('kind'))} · ~{esc(beat.get('estimated_minutes'))} min</p>"
            f"<p>{esc(beat.get('purpose'))}</p><div class='evidence-row'>{''.join(evidence_html) or '<span class=\"evidence none\">sin evidencia actual</span>'}</div></div></article>"
        )

    source_rows = []
    for index, item in enumerate(selected_items, start=1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "") or "")
        title = esc(item.get("title"))
        source_title = f"<a href='{esc(url)}' target='_blank' rel='noreferrer'>{title}</a>" if url else title
        source_rows.append(
            f"<tr><td>{index}</td><td>{source_title}</td><td>{esc(item.get('source'))}</td>"
            f"<td><span class='badge neutral'>{esc(item.get('url_quality'))}</span></td><td>{esc(item.get('news_id'))}</td></tr>"
        )

    media_cards = []
    for item in sorted(
        (manifest if isinstance(manifest, list) else []),
        key=lambda value: float(value.get("start_seconds", 0) or 0),
    ):
        rel = str(item.get("file", "") or "")
        if not rel:
            continue
        asset_type = str(item.get("asset_type", "image") or "image")
        preview = _render_media_preview(item, rel)
        media_cards.append(
            "<article class='media-card'>"
            f"{preview}"
            f"<div class='media-meta'><div><span class='badge neutral'>{esc(asset_type.upper())}</span> <strong>{esc(item.get('section_key') or item.get('beat_id'))}</strong></div>"
            f"<span>{esc(item.get('on_screen_text') or item.get('visual_query'))}</span>"
            f"<small>{esc(item.get('start_seconds'))}–{esc(item.get('end_seconds'))}s · {esc(item.get('provider'))} · {esc(item.get('license'))}</small>"
            f"<small>priority {esc(item.get('slot_priority'))} · preferred {esc(item.get('preferred_asset_type'))}</small>"
            f"<a class='button small secondary' href='media/{esc(rel)}' download>Descargar pieza</a></div></article>"
        )

    history_rows = []
    for item in history:
        verdict = bool_badge(bool(item.get("publishable")), true_text="VALIDADO", false_text="RECHAZADO")
        href = str(item.get("href", ""))
        link = f"<a class='button small' href='{esc(href)}'>Leer TXT</a>" if href else "—"
        reasons = "; ".join(str(v) for v in item.get("rejection_reasons", [])[:3])
        history_rows.append(
            f"<tr><td>{esc(item.get('case_id'))}</td><td>{esc(item.get('run_id'))}</td><td>{verdict}</td><td>{esc(reasons)}</td><td>{link}</td></tr>"
        )

    artifact_links = "".join(
        f"<a class='artifact-link' href='artifacts/{name}'>{name}</a>"
        for name in (
            "episode_plan.json", "script_sections.json", "reviews.json", "run_state.json",
            "selected_news.json", "novelty_check.json", "editorial-regression.json",
            "media-plan.json", "media-manifest.json", "credits.md",
        )
        if (output_dir / "artifacts" / name).exists()
    )

    html_doc = f"""<!doctype html>
<html lang='es'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>AI News Daily · Editorial Review Hub</title>
<style>
:root{{--bg:#0a0d12;--panel:#121722;--panel2:#171e2b;--text:#edf2f7;--muted:#9aa7b5;--line:#283244;--accent:#7dd3fc;--good:#34d399;--bad:#fb7185;--warn:#fbbf24}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(180deg,#080b10,#0d121a 35%,#090c12);color:var(--text);font:15px/1.65 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}} .wrap{{max-width:1160px;margin:auto;padding:48px 24px 96px}}
.hero{{padding:42px;border:1px solid var(--line);border-radius:24px;background:radial-gradient(circle at top right,#17344b 0,transparent 36%),var(--panel);box-shadow:0 20px 70px #0007}} .eyebrow{{color:var(--accent);text-transform:uppercase;letter-spacing:.14em;font-weight:800;font-size:12px}} h1{{font-size:clamp(32px,5vw,60px);line-height:1.02;margin:.3em 0}} h2{{font-size:28px;margin-top:52px}} h3{{margin:0 0 4px}} h4{{margin:8px 0}} .lede{{font-size:19px;color:#c7d2df;max-width:850px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0}} .metric{{background:var(--panel2);border:1px solid var(--line);border-radius:16px;padding:16px}} .metric strong{{display:block;font-size:26px}} .metric span{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}}
.badge{{display:inline-block;border-radius:999px;padding:4px 9px;font-weight:800;font-size:11px;letter-spacing:.05em}} .badge.ok{{background:#123b31;color:#8df0c9}} .badge.bad{{background:#451d2a;color:#ffafbd}} .badge.neutral{{background:#202938;color:#bfd0e3}} .review-box{{border:1px solid #3b4b63;background:#111927;border-radius:20px;padding:24px;margin-top:22px}} code{{background:#151c28;padding:2px 6px;border-radius:6px}}
.grid2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}} .card{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:22px}} .card p:last-child{{margin-bottom:0}} .muted{{color:var(--muted)}}
.button{{display:inline-block;background:var(--accent);color:#07121a!important;font-weight:850;border-radius:12px;padding:11px 16px;margin:4px 6px 4px 0;text-decoration:none!important}} .button.secondary{{background:#202b3b;color:#e5eef8!important;border:1px solid #334258}} .button.small{{font-size:12px;padding:6px 10px}}
.script{{white-space:pre-wrap;background:#0c1119;border:1px solid var(--line);border-radius:18px;padding:28px;font-family:Georgia,serif;font-size:17px;line-height:1.82;max-height:900px;overflow:auto}} .beat{{display:grid;grid-template-columns:52px 1fr;gap:14px;padding:20px 0;border-bottom:1px solid var(--line)}} .beat-no{{font-size:22px;color:var(--accent);font-weight:900}} .evidence-row{{display:flex;gap:7px;flex-wrap:wrap}} .evidence{{font-size:12px;background:#172738;border:1px solid #27435e;border-radius:999px;padding:5px 9px}} .evidence.none{{background:#242631;border-color:#383b49;color:#aeb6c0}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line)}} th,td{{padding:12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}} th{{color:#b9c6d4;font-size:12px;text-transform:uppercase;letter-spacing:.06em}} .table-wrap{{overflow:auto;border-radius:16px}}
.media-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}} .media-card{{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden}} .media-card img,.media-card video{{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#111}} .media-meta{{padding:12px;display:grid;gap:6px}} .media-meta small{{color:var(--muted)}} .artifact-link{{display:inline-block;margin:5px 8px 5px 0;background:#141c28;border:1px solid var(--line);padding:7px 10px;border-radius:9px;font-size:12px}} .review-notes{{background:#101722;border-left:3px solid var(--warn);padding:10px 16px;margin:12px 0;border-radius:4px 12px 12px 4px}} .footer{{margin-top:60px;color:var(--muted);border-top:1px solid var(--line);padding-top:24px}}
@media(max-width:600px){{.hero{{padding:26px}} .wrap{{padding:24px 14px 70px}} .script{{padding:18px;font-size:16px}}}}
</style>
</head>
<body><main class='wrap'>
<section class='hero'>
<div class='eyebrow'>AI News Daily · Editorial Review Hub</div>
<h1>{esc(plan.get('topic_signature') or 'Último ensayo generado')}</h1>
<p class='lede'>{esc(plan.get('central_question'))}</p>
<div>{bool_badge(state.get('publishable'), true_text='PUBLICABLE', false_text=str(state.get('status','PENDING')).upper())}</div>
<div class='metrics'>
<div class='metric'><strong>{words}</strong><span>palabras</span></div><div class='metric'><strong>{minutes:.1f}</strong><span>min estimados</span></div>
<div class='metric'><strong>{score(editorial.get('score'))}</strong><span>Editorial</span></div><div class='metric'><strong>{score(seo.get('score'))}</strong><span>SEO</span></div>
<div class='metric'><strong>{score(attention.get('score'))}</strong><span>Attention</span></div><div class='metric'><strong>{score(voice.get('score'))}</strong><span>Voice</span></div>
<div class='metric'><strong>{opening_media_count}</strong><span>media 0–20s</span></div><div class='metric'><strong>{opening_video_count}</strong><span>videos 0–20s</span></div>
</div>
<div class='review-box'><strong>Human review pendiente · ID <code>{esc(validation_id)}</code></strong><p>Para incorporarlo al corpus humano, responde en ChatGPT con <code>VALIDADO {esc(validation_id)}</code> o <code>RECHAZADO {esc(validation_id)}</code> y, si quieres, una razón breve.</p>
<a class='button' href='scripts/latest-{esc(validation_id)}.txt'>Descargar guion TXT</a><a class='button secondary' href='downloads/{esc(media_zip_name)}'>Descargar multimedia ZIP</a></div>
</section>

<h2>Lectura del guion</h2><div class='script'>{esc(script)}</div>

<h2>Arquitectura narrativa</h2><div class='grid2'>
<div class='card'><h3>Creencia inicial</h3><p>{esc(arc.get('opening_belief'))}</p><h3>Misterio</h3><p>{esc(arc.get('central_mystery'))}</p><h3>Giro</h3><p>{esc(arc.get('narrative_turn'))}</p></div>
<div class='card'><h3>Tesis provisional</h3><p>{esc(plan.get('thesis'))}</p><h3>Tesis evolucionada</h3><p>{esc(arc.get('evolved_thesis'))}</p><h3>Payoff</h3><p>{esc(arc.get('final_payoff'))}</p></div></div>
<div class='card' style='margin-top:18px'><strong>Motivo recurrente:</strong> {esc(arc.get('recurring_motif'))}<br><strong>Human peak:</strong> {esc(arc.get('emotional_peak'))}<br><strong>Closing question:</strong> {esc(plan.get('closing_question'))}</div>

<h2>Beats del ensayo</h2><section class='card'>{''.join(beat_rows)}</section>

<h2>Evaluación automática</h2><div class='grid2'>
<div class='card'><h3>Editorial {score(editorial.get('score'))} · {bool_badge(editorial.get('approved'))}</h3>{problems_block('Problemas / mejoras', editorial)}</div>
<div class='card'><h3>Voice {score(voice.get('score'))} · {bool_badge(voice.get('approved'))}</h3><p class='muted'>Fidelity {score(voice.get('voice_fidelity'))} · Depth {score(voice.get('intellectual_depth'))} · Human {score(voice.get('human_relevance'))} · Analogy {score(voice.get('analogy_quality'))} · AI smell {esc(voice.get('ai_smell_risk'))}</p>{problems_block('Problemas / mejoras', voice)}</div>
<div class='card'><h3>Attention {score(attention.get('score'))} · {bool_badge(attention.get('approved'))}</h3>{problems_block('Problemas / mejoras', attention)}</div>
<div class='card'><h3>SEO {score(seo.get('score'))} · {bool_badge(seo.get('approved'))}</h3>{problems_block('Problemas / mejoras', seo)}</div></div>
<p class='muted'>Best candidate: iteración {esc(best.get('iteration'))}, {esc(best.get('judged_unique_script_count'))} guiones únicos juzgados. Structural regression: {esc(regression.get('structural_pass'))}. Novelty attempts: {len(novelty.get('attempts',[]) if isinstance(novelty,dict) else [])}.</p>

<h2>Fuentes seleccionadas</h2><div class='table-wrap'><table><thead><tr><th>#</th><th>Título</th><th>Fuente</th><th>URL quality</th><th>ID</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div>

<h2>Multimedia de revisión</h2><p>Los primeros 20 segundos se tratan como cold open de alta densidad visual: objetivo mínimo de cinco piezas, con prioridad a video y cambios cada ~3–4 segundos. Después del segundo 20 la multimedia vuelve a ser selectiva y explicativa.</p>
<p>Cold open actual: <strong>{opening_media_count}</strong> piezas, de las cuales <strong>{opening_video_count}</strong> son video. Paquete total: <strong>{len(manifest) if isinstance(manifest,list) else 0}</strong> assets.</p>
<p><a class='button' href='downloads/{esc(media_zip_name)}'>Descargar ZIP completo</a><a class='button secondary' href='artifacts/credits.md'>Ver créditos/licencias</a></p>
<div class='media-grid'>{''.join(media_cards) or '<div class="card">No hubo assets descargables; revisa media-plan.json.</div>'}</div>

<h2>Guiones anteriores y veredicto humano</h2><div class='table-wrap'><table><thead><tr><th>Caso</th><th>Run</th><th>Humano</th><th>Motivo</th><th>Guion</th></tr></thead><tbody>{''.join(history_rows)}</tbody></table></div>

<h2>Artefactos técnicos</h2><div>{artifact_links}</div>
<div class='footer'>Run {esc(run_id)} · episodio {esc(target_date)} · Review hub generado determinísticamente a partir del artifact de Editorial Regression. El paquete multimedia es de revisión y no altera el estado de aprobación del episodio.</div>
</main></body></html>"""
    index_path = output_dir / "index.html"
    index_path.write_text(html_doc, encoding="utf-8")
    (output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the static AI News Daily editorial review hub")
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--media-dir", required=True)
    parser.add_argument("--media-zip", required=True)
    parser.add_argument("--regression", required=True)
    parser.add_argument("--cases", default="evals/editorial/cases.json")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


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
