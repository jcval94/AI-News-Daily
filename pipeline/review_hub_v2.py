from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from string import Template
from typing import Any

from pipeline.core import PipelineConfig

CONFIG = PipelineConfig.from_env()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def search_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(item) for item in value)
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
        else:
            parts.append(str(value or ""))
    return esc(" ".join(parts))


def score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def bool_badge(value: Any, *, true_text: str = "PASS", false_text: str = "FAIL") -> str:
    ok = bool(value)
    klass = "ok" if ok else "bad"
    return f'<span class="badge {klass}">{esc(true_text if ok else false_text)}</span>'


def copy_file(source: Path, destination: Path) -> bool:
    if not source.exists() or not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def problems_block(label: str, review: dict[str, Any]) -> str:
    items = list(review.get("problems", []) or []) + list(review.get("improvements", []) or [])
    if not items:
        return "<p class='muted'>Sin observaciones adicionales.</p>"
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
    duration_seconds = int(
        (reviews.get("gate", {}) or {}).get("duration_seconds", 0)
        or round(words / CONFIG.words_per_second)
    )
    minutes = duration_seconds / 60.0
    opening_media_count = int(media_plan.get("opening_media_count", 0) or 0) if isinstance(media_plan, dict) else 0
    opening_video_count = int(media_plan.get("opening_video_count", 0) or 0) if isinstance(media_plan, dict) else 0

    script_download = output_dir / "scripts" / f"latest-{validation_id}.txt"
    copy_file(episode_dir / "script.txt", script_download)
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

    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in plan.get("evidence", []) if isinstance(item, dict)
    }
    selected_items = selected.get("items", []) if isinstance(selected, dict) else []

    beat_rows: list[str] = []
    for index, beat in enumerate(plan.get("beats", []) if isinstance(plan, dict) else [], start=1):
        if not isinstance(beat, dict):
            continue
        evidence_html: list[str] = []
        evidence_search: list[str] = []
        for evidence_id in beat.get("evidence_ids", []) or []:
            evidence = evidence_by_id.get(str(evidence_id), {})
            selected_index = int(evidence.get("selected_news_index", 0) or 0)
            title = ""
            if 1 <= selected_index <= len(selected_items) and isinstance(selected_items[selected_index - 1], dict):
                title = str(selected_items[selected_index - 1].get("title", "") or "")
            evidence_search.extend([str(evidence_id), title])
            evidence_html.append(
                f"<span class='evidence'>{esc(evidence_id)}{': ' + esc(title) if title else ''}</span>"
            )
        blob = search_blob(
            beat.get("beat_id"), beat.get("kind"), beat.get("purpose"), beat.get("estimated_minutes"), evidence_search
        )
        beat_rows.append(
            f"<article class='beat searchable-card' data-search-item data-search-text='{blob}'>"
            f"<div class='beat-no'>{index:02d}</div><div><h3>{esc(beat.get('beat_id'))}</h3>"
            f"<p class='muted'>{esc(beat.get('kind'))} · ~{esc(beat.get('estimated_minutes'))} min</p>"
            f"<p>{esc(beat.get('purpose'))}</p>"
            f"<div class='evidence-row'>{''.join(evidence_html) or '<span class=\"evidence none\">sin evidencia actual</span>'}</div>"
            "</div></article>"
        )

    source_rows: list[str] = []
    for index, item in enumerate(selected_items, start=1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "") or "")
        title = esc(item.get("title"))
        source_title = f"<a href='{esc(url)}' target='_blank' rel='noreferrer'>{title}</a>" if url else title
        blob = search_blob(item)
        source_rows.append(
            f"<tr data-search-item data-search-text='{blob}'><td>{index}</td><td>{source_title}</td>"
            f"<td>{esc(item.get('source'))}</td><td><span class='badge neutral'>{esc(item.get('url_quality'))}</span></td>"
            f"<td>{esc(item.get('news_id'))}</td></tr>"
        )

    media_cards: list[str] = []
    for item in sorted(
        (manifest if isinstance(manifest, list) else []),
        key=lambda value: float(value.get("start_seconds", 0) or 0),
    ):
        rel = str(item.get("file", "") or "")
        if not rel:
            continue
        asset_type = str(item.get("asset_type", "image") or "image")
        preview = _render_media_preview(item, rel)
        blob = search_blob(item, rel)
        media_cards.append(
            f"<article class='media-card searchable-card' data-search-item data-search-text='{blob}'>"
            f"{preview}<div class='media-meta'><div><span class='badge neutral'>{esc(asset_type.upper())}</span> "
            f"<strong>{esc(item.get('section_key') or item.get('beat_id'))}</strong></div>"
            f"<span>{esc(item.get('on_screen_text') or item.get('visual_query'))}</span>"
            f"<small>{esc(item.get('start_seconds'))}–{esc(item.get('end_seconds'))}s · {esc(item.get('provider'))} · {esc(item.get('license'))}</small>"
            f"<small>priority {esc(item.get('slot_priority'))} · preferred {esc(item.get('preferred_asset_type'))}</small>"
            f"<a class='button small secondary' href='media/{esc(rel)}' download>Descargar pieza</a></div></article>"
        )

    history_rows: list[str] = []
    for item in history:
        verdict = bool_badge(bool(item.get("publishable")), true_text="VALIDADO", false_text="RECHAZADO")
        href = str(item.get("href", ""))
        link = f"<a class='button small' href='{esc(href)}'>Leer TXT</a>" if href else "—"
        reasons = "; ".join(str(v) for v in item.get("rejection_reasons", [])[:3])
        blob = search_blob(item)
        history_rows.append(
            f"<tr data-search-item data-search-text='{blob}'><td>{esc(item.get('case_id'))}</td>"
            f"<td>{esc(item.get('run_id'))}</td><td>{verdict}</td><td>{esc(reasons)}</td><td>{link}</td></tr>"
        )

    artifact_links = "".join(
        f"<a class='artifact-link' data-search-item data-search-text='{esc(name)}' href='artifacts/{name}'>{name}</a>"
        for name in (
            "episode_plan.json",
            "script_sections.json",
            "reviews.json",
            "run_state.json",
            "selected_news.json",
            "novelty_check.json",
            "editorial-regression.json",
            "media-plan.json",
            "media-manifest.json",
            "credits.md",
        )
        if (output_dir / "artifacts" / name).exists()
    )

    review_cards = "".join(
        [
            f"<div class='card searchable-card' data-search-item data-search-text='{search_blob('Editorial', editorial)}'><h3>Editorial {score(editorial.get('score'))} · {bool_badge(editorial.get('approved'))}</h3>{problems_block('Problemas / mejoras', editorial)}</div>",
            f"<div class='card searchable-card' data-search-item data-search-text='{search_blob('Voice', voice)}'><h3>Voice {score(voice.get('score'))} · {bool_badge(voice.get('approved'))}</h3><p class='muted'>Fidelity {score(voice.get('voice_fidelity'))} · Depth {score(voice.get('intellectual_depth'))} · Human {score(voice.get('human_relevance'))} · Analogy {score(voice.get('analogy_quality'))} · AI smell {esc(voice.get('ai_smell_risk'))}</p>{problems_block('Problemas / mejoras', voice)}</div>",
            f"<div class='card searchable-card' data-search-item data-search-text='{search_blob('Attention', attention)}'><h3>Attention {score(attention.get('score'))} · {bool_badge(attention.get('approved'))}</h3>{problems_block('Problemas / mejoras', attention)}</div>",
            f"<div class='card searchable-card' data-search-item data-search-text='{search_blob('SEO', seo)}'><h3>SEO {score(seo.get('score'))} · {bool_badge(seo.get('approved'))}</h3>{problems_block('Problemas / mejoras', seo)}</div>",
        ]
    )

    template = Template(r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI News Daily · Editorial Review Hub</title>
<style>
:root{--bg:#090c12;--panel:#111722;--panel2:#151d2a;--text:#eef3f8;--muted:#98a6b5;--line:#283344;--accent:#7dd3fc;--good:#34d399;--bad:#fb7185;--warn:#fbbf24;--mark:#fef08a}
*{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;background:linear-gradient(180deg,#080b10,#0d121a 38%,#090c12);color:var(--text);font:15px/1.65 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}.wrap{max-width:1120px;margin:auto;padding:34px 24px 90px}
.hero{padding:30px 32px;border:1px solid var(--line);border-radius:22px;background:radial-gradient(circle at top right,#17344b 0,transparent 34%),var(--panel);box-shadow:0 18px 60px #0006}.eyebrow{color:var(--accent);text-transform:uppercase;letter-spacing:.14em;font-weight:800;font-size:11px}.hero h1{font-size:clamp(30px,4.5vw,52px);line-height:1.05;margin:.28em 0 .2em;max-width:900px}.lede{font-size:18px;color:#c7d2df;max-width:820px;margin:0 0 18px}.hero-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.hero-actions{margin-top:18px}.hero-meta{margin-top:12px;color:var(--muted);font-size:12px}
h2{font-size:27px;margin:48px 0 16px}h3{margin:0 0 5px}h4{margin:8px 0}.muted{color:var(--muted)}code{background:#151c28;padding:2px 6px;border-radius:6px}
.button{display:inline-block;background:var(--accent);color:#07121a!important;font-weight:850;border-radius:11px;padding:10px 15px;margin:3px 6px 3px 0;text-decoration:none!important}.button.secondary{background:#202b3b;color:#e5eef8!important;border:1px solid #334258}.button.small{font-size:12px;padding:6px 10px}
.badge{display:inline-block;border-radius:999px;padding:4px 9px;font-weight:800;font-size:11px;letter-spacing:.05em}.badge.ok{background:#123b31;color:#8df0c9}.badge.bad{background:#451d2a;color:#ffafbd}.badge.neutral{background:#202938;color:#bfd0e3}
.search-dock{position:sticky;top:10px;z-index:20;margin:18px 0 22px;padding:10px;border:1px solid #334258;border-radius:16px;background:#0d141ed9;backdrop-filter:blur(12px);box-shadow:0 10px 30px #0005}.search-row{display:flex;gap:9px;align-items:center}.search-row input{width:100%;border:1px solid #34445b;background:#0a1018;color:var(--text);border-radius:11px;padding:11px 13px;font:inherit;outline:none}.search-row input:focus{border-color:var(--accent);box-shadow:0 0 0 3px #7dd3fc20}.search-count{white-space:nowrap;color:var(--muted);font-size:12px}.quick-nav{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.quick-nav a{font-size:12px;background:#151e2b;border:1px solid #28374b;border-radius:999px;padding:4px 9px;color:#c7d6e6}
.card{background:var(--panel);border:1px solid var(--line);border-radius:17px;padding:20px}.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}.script{white-space:pre-wrap;background:#0c1119;border:1px solid var(--line);border-radius:17px;padding:27px;font-family:Georgia,serif;font-size:17px;line-height:1.84;max-height:920px;overflow:auto}.script mark{background:var(--mark);color:#171717;padding:0 2px;border-radius:2px}.beat{display:grid;grid-template-columns:48px 1fr;gap:14px;padding:18px 0;border-bottom:1px solid var(--line)}.beat:last-child{border-bottom:0}.beat-no{font-size:21px;color:var(--accent);font-weight:900}.evidence-row{display:flex;gap:7px;flex-wrap:wrap}.evidence{font-size:12px;background:#172738;border:1px solid #27435e;border-radius:999px;padding:5px 9px}.evidence.none{background:#242631;border-color:#383b49;color:#aeb6c0}
details.diagnostic{border:1px solid var(--line);border-radius:17px;background:var(--panel);overflow:hidden}details.diagnostic>summary{cursor:pointer;padding:18px 20px;font-weight:800;list-style:none}details.diagnostic>summary::-webkit-details-marker{display:none}.diagnostic-body{padding:0 20px 20px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px;margin-bottom:16px}.metric{background:var(--panel2);border:1px solid var(--line);border-radius:13px;padding:12px}.metric strong{display:block;font-size:21px}.metric span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}.review-notes{background:#101722;border-left:3px solid var(--warn);padding:9px 14px;margin:11px 0;border-radius:4px 11px 11px 4px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line)}th,td{padding:11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:#b9c6d4;font-size:11px;text-transform:uppercase;letter-spacing:.06em}.table-wrap{overflow:auto;border-radius:15px}
.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:13px}.media-card{background:var(--panel);border:1px solid var(--line);border-radius:15px;overflow:hidden}.media-card img,.media-card video{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#111}.media-meta{padding:11px;display:grid;gap:5px}.media-meta small{color:var(--muted)}.artifact-link{display:inline-block;margin:5px 7px 5px 0;background:#141c28;border:1px solid var(--line);padding:7px 10px;border-radius:9px;font-size:12px}.footer{margin-top:55px;color:var(--muted);border-top:1px solid var(--line);padding-top:22px}.no-results{padding:18px;border:1px dashed #4a5769;border-radius:14px;color:var(--muted);text-align:center}[hidden]{display:none!important}
@media(max-width:600px){.wrap{padding:20px 13px 65px}.hero{padding:23px}.hero h1{font-size:32px}.script{padding:17px;font-size:16px}.search-row{align-items:stretch;flex-direction:column}.search-count{padding-left:3px}.search-dock{top:4px}}
</style>
</head>
<body><main class="wrap">
<section class="hero">
<div class="eyebrow">AI News Daily · Editorial Review Hub</div>
<h1>$title</h1>
<p class="lede">$question</p>
<div class="hero-row">$status_badge <span class="muted">$words palabras · $minutes min · $opening_media media / $opening_videos videos en 0–20s</span></div>
<div class="hero-actions"><a class="button" href="$script_href">Leer / descargar guion</a><a class="button secondary" href="downloads/$zip_name">Descargar multimedia ZIP</a></div>
<div class="hero-meta">Human review · <code>$validation_id</code> · responde en ChatGPT con VALIDADO o RECHAZADO + este ID.</div>
</section>

<section class="search-dock" aria-label="Buscador del review hub">
<div class="search-row"><input id="globalSearch" type="search" autocomplete="off" placeholder="Buscar en guion, beats, fuentes, críticas, multimedia…" aria-label="Buscar en el review hub"><span id="searchCount" class="search-count">Busca en todo el hub</span></div>
<nav class="quick-nav"><a href="#guion">Guion</a><a href="#arquitectura">Arquitectura</a><a href="#beats">Beats</a><a href="#diagnostico">Diagnóstico</a><a href="#fuentes">Fuentes</a><a href="#multimedia">Multimedia</a></nav>
</section>
<div id="noResults" class="no-results" hidden>No encontré coincidencias. Prueba otro término.</div>

<section id="guion" data-search-group><h2>Guion actual</h2><div id="scriptText" class="script" data-search-script>$script</div></section>

<section id="arquitectura" data-search-group><h2>Arquitectura narrativa</h2><div class="grid2">
<div class="card searchable-card" data-search-item data-search-text="$arc_search_a"><h3>Creencia inicial</h3><p>$opening_belief</p><h3>Misterio</h3><p>$central_mystery</p><h3>Giro</h3><p>$narrative_turn</p></div>
<div class="card searchable-card" data-search-item data-search-text="$arc_search_b"><h3>Tesis provisional</h3><p>$thesis</p><h3>Tesis evolucionada</h3><p>$evolved_thesis</p><h3>Payoff</h3><p>$final_payoff</p></div>
</div><div class="card searchable-card" data-search-item data-search-text="$arc_search_c" style="margin-top:16px"><strong>Motivo:</strong> $motif<br><strong>Human peak:</strong> $human_peak<br><strong>Cierre:</strong> $closing_question</div></section>

<section id="beats" data-search-group><h2>Beats del ensayo</h2><div class="card">$beat_rows</div></section>

<section id="diagnostico" data-search-group><h2>Diagnóstico</h2><details class="diagnostic"><summary>Ver scores, gates y observaciones de los jueces</summary><div class="diagnostic-body">
<div class="metrics"><div class="metric"><strong>$editorial_score</strong><span>Editorial</span></div><div class="metric"><strong>$seo_score</strong><span>SEO</span></div><div class="metric"><strong>$attention_score</strong><span>Attention</span></div><div class="metric"><strong>$voice_score</strong><span>Voice</span></div><div class="metric"><strong>$opening_media</strong><span>media 0–20s</span></div><div class="metric"><strong>$opening_videos</strong><span>videos 0–20s</span></div></div>
<div class="grid2">$review_cards</div><p class="muted">Best candidate: iteración $best_iteration · $unique_scripts guiones únicos juzgados. Structural regression: $structural_pass. Novelty attempts: $novelty_attempts.</p></div></details></section>

<section id="fuentes" data-search-group><h2>Fuentes seleccionadas</h2><div class="table-wrap"><table><thead><tr><th>#</th><th>Título</th><th>Fuente</th><th>URL quality</th><th>ID</th></tr></thead><tbody>$source_rows</tbody></table></div></section>

<section id="multimedia" data-search-group><h2>Multimedia de revisión</h2><p>Cold open: <strong>$opening_media</strong> piezas, <strong>$opening_videos</strong> videos. Después del segundo 20, la cobertura vuelve a ser selectiva y explicativa. Total: <strong>$asset_count</strong> assets.</p><p><a class="button" href="downloads/$zip_name">Descargar ZIP completo</a><a class="button secondary" href="artifacts/credits.md">Créditos / licencias</a></p><div class="media-grid">$media_cards</div></section>

<section id="historial" data-search-group><h2>Guiones anteriores</h2><div class="table-wrap"><table><thead><tr><th>Caso</th><th>Run</th><th>Humano</th><th>Motivo</th><th>Guion</th></tr></thead><tbody>$history_rows</tbody></table></div></section>

<section id="artefactos" data-search-group><h2>Artefactos técnicos</h2><div>$artifact_links</div></section>
<div class="footer">Run $run_id · episodio $target_date · El paquete multimedia es de revisión y no altera el estado editorial.</div>
</main>
<script>
(() => {
  const input = document.getElementById('globalSearch');
  const count = document.getElementById('searchCount');
  const noResults = document.getElementById('noResults');
  const scriptNode = document.getElementById('scriptText');
  const scriptOriginal = scriptNode.textContent;
  const items = Array.from(document.querySelectorAll('[data-search-item]'));
  const groups = Array.from(document.querySelectorAll('[data-search-group]'));

  const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const normalizedScript = norm(scriptOriginal);

  function highlightScript(rawQuery) {
    scriptNode.textContent = '';
    if (!rawQuery) {
      scriptNode.textContent = scriptOriginal;
      return 0;
    }
    const q = norm(rawQuery);
    if (!q) {
      scriptNode.textContent = scriptOriginal;
      return 0;
    }
    let normalized = '';
    const map = [];
    for (let i = 0; i < scriptOriginal.length; i++) {
      const chunk = scriptOriginal[i].normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
      for (const char of chunk) {
        normalized += char;
        map.push(i);
      }
    }
    let cursorNorm = 0;
    let cursorOriginal = 0;
    let matches = 0;
    while (true) {
      const at = normalized.indexOf(q, cursorNorm);
      if (at < 0) break;
      const startOriginal = map[at];
      const endOriginal = map[Math.min(map.length - 1, at + q.length - 1)] + 1;
      scriptNode.appendChild(document.createTextNode(scriptOriginal.slice(cursorOriginal, startOriginal)));
      const mark = document.createElement('mark');
      mark.textContent = scriptOriginal.slice(startOriginal, endOriginal);
      scriptNode.appendChild(mark);
      cursorOriginal = endOriginal;
      cursorNorm = at + q.length;
      matches += 1;
    }
    scriptNode.appendChild(document.createTextNode(scriptOriginal.slice(cursorOriginal)));
    return matches;
  }

  function applySearch() {
    const raw = input.value.trim();
    const q = norm(raw);
    let matchedItems = 0;
    items.forEach(item => {
      const haystack = norm(item.dataset.searchText || item.textContent);
      const show = !q || haystack.includes(q);
      item.hidden = !show;
      if (q && show) matchedItems += 1;
    });
    const scriptMatches = highlightScript(raw);
    groups.forEach(group => {
      if (!q) {
        group.hidden = false;
        return;
      }
      if (group.id === 'guion') {
        group.hidden = scriptMatches === 0 && !normalizedScript.includes(q);
        return;
      }
      const children = Array.from(group.querySelectorAll('[data-search-item]'));
      group.hidden = children.length > 0 && children.every(child => child.hidden);
    });
    const total = matchedItems + scriptMatches;
    count.textContent = q ? (String(total) + ' coincidencia' + (total === 1 ? '' : 's')) : 'Busca en todo el hub';
    noResults.hidden = !q || total > 0;
  }

  input.addEventListener('input', applySearch);
  document.addEventListener('keydown', event => {
    if (event.key === '/' && document.activeElement !== input) {
      event.preventDefault();
      input.focus();
    }
    if (event.key === 'Escape' && document.activeElement === input) {
      input.value = '';
      applySearch();
      input.blur();
    }
  });
})();
</script>
</body></html>""")

    html_doc = template.substitute(
        title=esc(plan.get("topic_signature") or "Último ensayo generado"),
        question=esc(plan.get("central_question")),
        status_badge=bool_badge(state.get("publishable"), true_text="PUBLICABLE", false_text=str(state.get("status", "PENDING")).upper()),
        words=str(words),
        minutes=f"{minutes:.1f}",
        opening_media=str(opening_media_count),
        opening_videos=str(opening_video_count),
        script_href=f"scripts/latest-{esc(validation_id)}.txt",
        zip_name=esc(media_zip_name),
        validation_id=esc(validation_id),
        script=esc(script),
        arc_search_a=search_blob(arc.get("opening_belief"), arc.get("central_mystery"), arc.get("narrative_turn")),
        opening_belief=esc(arc.get("opening_belief")),
        central_mystery=esc(arc.get("central_mystery")),
        narrative_turn=esc(arc.get("narrative_turn")),
        arc_search_b=search_blob(plan.get("thesis"), arc.get("evolved_thesis"), arc.get("final_payoff")),
        thesis=esc(plan.get("thesis")),
        evolved_thesis=esc(arc.get("evolved_thesis")),
        final_payoff=esc(arc.get("final_payoff")),
        arc_search_c=search_blob(arc.get("recurring_motif"), arc.get("emotional_peak"), plan.get("closing_question")),
        motif=esc(arc.get("recurring_motif")),
        human_peak=esc(arc.get("emotional_peak")),
        closing_question=esc(plan.get("closing_question")),
        beat_rows="".join(beat_rows),
        editorial_score=score(editorial.get("score")),
        seo_score=score(seo.get("score")),
        attention_score=score(attention.get("score")),
        voice_score=score(voice.get("score")),
        review_cards=review_cards,
        best_iteration=esc(best.get("iteration")),
        unique_scripts=esc(best.get("judged_unique_script_count")),
        structural_pass=esc(regression.get("structural_pass")),
        novelty_attempts=str(len(novelty.get("attempts", []) if isinstance(novelty, dict) else [])),
        source_rows="".join(source_rows),
        asset_count=str(len(manifest) if isinstance(manifest, list) else 0),
        media_cards="".join(media_cards) or '<div class="card">No hubo assets descargables; revisa media-plan.json.</div>',
        history_rows="".join(history_rows),
        artifact_links=artifact_links,
        run_id=esc(run_id),
        target_date=esc(target_date),
    )

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
