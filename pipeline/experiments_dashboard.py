from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from pipeline.review_hub_v12 import apply_script_editor
from pipeline.review_hub_v13 import apply_script_productivity


DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
EXPERIMENT_TITLES = {"notebook_story_flow": "Epopeya abierta"}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _slug(value: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:72] or "run"
    return f"{readable}-{hashlib.sha256(value.encode()).hexdigest()[:8]}"


def _placements(sections: list[dict[str, Any]], predicate: Any) -> list[dict[str, str]]:
    found = []
    for section in sections:
        if not predicate(section):
            continue
        start, end = section.get("start_seconds"), section.get("end_seconds")
        timing = f"{start}–{end} s" if start is not None and end is not None else ""
        excerpt = " ".join(str(section.get("text") or section.get("spoken_text") or "").split())[:180]
        found.append({"section": str(section.get("id") or section.get("section_key") or "sección"), "timing": timing, "excerpt": excerpt})
    return found


def _story_map(run_dir: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    section_payload = _read_json(run_dir / "script_sections.json")
    sections = section_payload.get("sections") if isinstance(section_payload.get("sections"), list) else []
    sections = [row for row in sections if isinstance(row, dict)]
    plan = {}
    for filename in ("story_plan.json", "experiment_plan.json", "episode_plan.json"):
        plan = _read_json(run_dir / filename)
        if plan:
            break

    stories: list[dict[str, Any]] = []
    memory_id = str(
        plan.get("selected_memory_id")
        or plan.get("primary_memory_id")
        or report.get("primary_memory_id")
        or ""
    )
    if memory_id:
        memory_sections = _placements(sections, lambda row: bool(row.get("memory_claim_indices")))
        narrative = section_payload.get("narrative_memory")
        if not memory_sections and isinstance(narrative, dict) and narrative.get("section_key"):
            memory_sections = [{"section": str(narrative["section_key"]), "timing": "", "excerpt": ""}]
        stories.append({"kind": "Historia histórica", "id": memory_id, "placements": memory_sections})

    ledger = plan.get("ledger") or plan.get("claim_ledger") or plan.get("evidence") or []
    for row in ledger if isinstance(ledger, list) else []:
        if not isinstance(row, dict):
            continue
        evidence_id = str(row.get("evidence_id") or "")
        if not evidence_id:
            continue
        stories.append(
            {
                "kind": "Evidencia actual",
                "id": evidence_id,
                "news_id": str(row.get("news_id") or ""),
                "placements": _placements(
                    sections,
                    lambda section, evidence_id=evidence_id: evidence_id in (section.get("evidence_ids") or []),
                ),
            }
        )
    return stories


def discover_experiments(roots: list[Path]) -> list[dict[str, Any]]:
    experiments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for report_path in sorted(root.rglob("run_report.json")):
            run_dir = report_path.parent
            relative = run_dir.relative_to(root)
            parts = [part for part in relative.parts if part not in {"results", "runs"}]
            report = _read_json(report_path)
            experiment_id = str(report.get("experiment") or (parts[0] if parts else run_dir.name))
            date_match = next((DATE_RE.search(part) for part in reversed(parts) if DATE_RE.search(part)), None)
            date = str(report.get("episode_date") or (date_match.group(0) if date_match else ""))
            run_id = "/".join(parts) or run_dir.name
            identity = f"{experiment_id}/{run_id}"
            if identity in seen:
                continue
            seen.add(identity)

            script_path = run_dir / "script.txt"
            script = script_path.read_text(encoding="utf-8").strip() if script_path.is_file() else ""
            review = _read_json(run_dir / "review.json") or _read_json(run_dir / "factual_review.json")
            gate = _read_json(run_dir / "deterministic_gate.json")
            report_gate = report.get("gate") if isinstance(report.get("gate"), dict) else {}
            checks = report_gate.get("checks") if isinstance(report_gate.get("checks"), dict) else {}
            checks = {str(key): bool(value) for key, value in checks.items()}
            if "passed" in gate:
                checks["deterministic_gate"] = bool(gate["passed"])
            if "publishable" in report:
                checks["publishable"] = bool(report["publishable"])
            problems = []
            for key in ("problems", "invented_details", "source_issues", "unsupported_claims"):
                if isinstance(review.get(key), list):
                    problems.extend(str(item) for item in review[key])
            if report.get("reason"):
                problems.insert(0, str(report["reason"]))
            experiments.append(
                {
                    "id": identity,
                    "slug": _slug(identity),
                    "experiment": experiment_id,
                    "title": EXPERIMENT_TITLES.get(experiment_id, _label(experiment_id)),
                    "date": date,
                    "run": parts[-1] if parts else run_dir.name,
                    "status": str(report.get("status") or "unknown"),
                    "score": review.get("score"),
                    "factuality_risk": review.get("factuality_risk") or review.get("risk"),
                    "word_count": report.get("word_count"),
                    "estimated_duration_seconds": report.get("estimated_duration_seconds"),
                    "words_per_minute": report.get("words_per_minute") or 150,
                    "has_script": bool(script),
                    "checks": checks,
                    "problems": problems,
                    "script": script,
                    "stories": _story_map(run_dir, report),
                }
            )
    experiments.sort(key=lambda item: (str(item["date"]), str(item["run"])), reverse=True)
    return experiments


def _metric(label: str, value: Any) -> str:
    display = "—" if value in (None, "") else str(value)
    return f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(display)}</dd></div>"


def _checks(item: dict[str, Any]) -> str:
    return "".join(
        f'<li class="{"pass" if passed else "fail"}">{"✓" if passed else "×"} {html.escape(_label(name))}</li>'
        for name, passed in item["checks"].items()
    ) or '<li class="muted">Sin gates reportados</li>'


def _card(item: dict[str, Any]) -> str:
    action = "Abrir mesa de guion" if item["script"] else "Ver resultado"
    return f"""<article class="experiment-card" data-experiment-card data-title="{html.escape(item['title'], quote=True)}" data-status="{html.escape(item['status'], quote=True)}" data-date="{html.escape(item['date'], quote=True)}" data-run="{html.escape(item['run'], quote=True)}">
  <header><div><span class="eyebrow">{html.escape(item['date'] or 'sin fecha')} · {html.escape(item['run'])}</span><h2>{html.escape(item['title'])}</h2></div><span class="status">{html.escape(_label(item['status']))}</span></header>
  <dl>{_metric('Score', item['score'])}{_metric('Riesgo factual', item['factuality_risk'])}{_metric('Palabras', item['word_count'])}{_metric('Duración', f"{item['estimated_duration_seconds']} s" if item['estimated_duration_seconds'] is not None else None)}</dl>
  <ul class="checks">{_checks(item)}</ul><a class="button primary" href="runs/{item['slug']}/index.html">{action}</a>
</article>"""


def dashboard_document(experiments: list[dict[str, Any]]) -> str:
    scripted = [item for item in experiments if item["has_script"]]
    without_script = [item for item in experiments if not item["has_script"]]
    experiment_options = "".join(
        f'<option value="{html.escape(title, quote=True)}">{html.escape(title)}</option>'
        for title in sorted({str(item["title"]) for item in experiments})
    )
    status_options = "".join(
        f'<option value="{html.escape(status, quote=True)}">{html.escape(_label(status))}</option>'
        for status in sorted({str(item["status"]) for item in experiments})
    )
    no_script_group = (
        f'<details class="archive" id="noScriptGroup"><summary>Sin guion <span id="noScriptCount">{len(without_script)} resultados</span></summary>'
        '<p class="muted">Intentos que terminaron antes de producir un guion. Haz clic para revisarlos.</p>'
        f'<section class="grid" data-card-grid>{"".join(_card(item) for item in without_script)}</section></details>'
        if without_script
        else ""
    )
    empty = "" if experiments else '<p class="empty">Todavía no hay resultados de experimentos publicados.</p>'
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>Experimentos · AI News Daily</title><style>{BASE_CSS}</style></head>
<body data-experiments-page="experiments"><main><span class="eyebrow">Laboratorio editorial</span><h1>Experimentos</h1><p class="lead">Resultados reproducibles, gates y mesas de guion editables. Incluye intentos fallidos para que el aprendizaje no desaparezca.</p>
<section class="toolbar" aria-label="Filtros de experimentos">
  <label class="search-field">Buscar<input id="experimentSearch" type="search" placeholder="Nombre, fecha, ejecución o estado…"></label>
  <label>Experimento<select id="experimentName"><option value="">Todos</option>{experiment_options}</select></label>
  <label>Estado<select id="experimentStatus"><option value="">Todos</option>{status_options}</select></label>
  <label>Orden<select id="experimentSort"><option value="newest">Más recientes</option><option value="oldest">Más antiguos</option><option value="title">Nombre A–Z</option><option value="status">Estado A–Z</option></select></label>
</section>
<p class="result-count" id="experimentCount" aria-live="polite"></p>
<section class="grid" id="scriptedExperiments" data-card-grid>{"".join(_card(item) for item in scripted)}</section>
<p class="empty" id="scriptedEmpty" hidden>No hay experimentos con guion que coincidan con los filtros.</p>{no_script_group}{empty}</main>
<script>
const search=document.getElementById('experimentSearch');
const nameFilter=document.getElementById('experimentName');
const statusFilter=document.getElementById('experimentStatus');
const sort=document.getElementById('experimentSort');
const cards=[...document.querySelectorAll('[data-experiment-card]')];
const archive=document.getElementById('noScriptGroup');
const compare=(a,b,key)=>a.dataset[key].localeCompare(b.dataset[key],'es',{{numeric:true,sensitivity:'base'}});
function refresh(){{
  const q=search.value.trim().toLocaleLowerCase('es');
  let visible=0,archived=0,scriptedVisible=0;
  cards.forEach(card=>{{
    const show=(!q||card.textContent.toLocaleLowerCase('es').includes(q))&&(!nameFilter.value||card.dataset.title===nameFilter.value)&&(!statusFilter.value||card.dataset.status===statusFilter.value);
    card.hidden=!show;
    if(show){{visible++;card.closest('#noScriptGroup')?archived++:scriptedVisible++;}}
  }});
  document.querySelectorAll('[data-card-grid]').forEach(grid=>{{
    [...grid.children].sort((a,b)=>sort.value==='oldest'?compare(a,b,'date')||compare(a,b,'run'):sort.value==='title'?compare(a,b,'title')||-compare(a,b,'date'):sort.value==='status'?compare(a,b,'status')||-compare(a,b,'date'):-compare(a,b,'date')||-compare(a,b,'run')).forEach(card=>grid.append(card));
  }});
  document.getElementById('experimentCount').textContent=`${{visible}} resultado${{visible===1?'':'s'}}`;
  document.getElementById('scriptedEmpty').hidden=cards.length===0||scriptedVisible>0;
  if(archive){{archive.hidden=archived===0;document.getElementById('noScriptCount').textContent=`${{archived}} resultado${{archived===1?'':'s'}}`;}}
}}
[search,nameFilter,statusFilter,sort].forEach(control=>control.addEventListener(control===search?'input':'change',refresh));
refresh();
</script></body></html>"""


def _story_map_html(stories: list[dict[str, Any]]) -> str:
    if not stories:
        return '<p class="muted">Este resultado no publicó metadatos de historias por sección.</p>'
    rows = []
    for story in stories:
        placements = "".join(
            f'<li><strong>{html.escape(_label(place["section"]))}</strong>'
            f'{f" <span>{html.escape(place["timing"])}</span>" if place["timing"] else ""}'
            f'{f"<p>{html.escape(place["excerpt"])}</p>" if place["excerpt"] else ""}</li>'
            for place in story["placements"]
        ) or '<li class="muted">Planificada, sin ubicación materializada.</li>'
        rows.append(
            f'<article class="story-card"><span class="story-kind">{html.escape(story["kind"])}</span>'
            f'<h3>{html.escape(_label(story["id"]))}</h3><code>{html.escape(story["id"])}</code><ul>{placements}</ul></article>'
        )
    return "".join(rows)


def run_document(item: dict[str, Any]) -> str:
    problems = "".join(f"<li>{html.escape(problem)}</li>" for problem in item["problems"])
    problem_block = f'<section class="panel"><h2>Hallazgos</h2><ul>{problems}</ul></section>' if problems else ""
    script_block = (
        '<section id="guion" data-search-group><h2>Guion actual</h2><div id="scriptText" class="script" data-search-script>'
        + html.escape(item["script"])
        + "</div></section>"
        if item["script"]
        else '<section class="panel"><h2>Guion</h2><p class="muted">Este intento terminó antes de producir un guion final editable.</p></section>'
    )
    document = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>{html.escape(item['title'])} · Experimentos</title><style>{BASE_CSS}</style></head><body data-experiment-run="{html.escape(item['slug'], quote=True)}"><main>
<a class="back" href="../../index.html">← Todos los experimentos</a><span class="eyebrow">{html.escape(item['date'] or 'sin fecha')} · {html.escape(item['run'])}</span><h1>{html.escape(item['title'])}</h1><span class="status">{html.escape(_label(item['status']))}</span>
<dl>{_metric('Score', item['score'])}{_metric('Riesgo factual', item['factuality_risk'])}{_metric('Palabras', item['word_count'])}{_metric('Duración', f"{item['estimated_duration_seconds']} s" if item['estimated_duration_seconds'] is not None else None)}</dl><ul class="checks">{_checks(item)}</ul>
<section class="panel"><h2>Mapa de historias</h2><p class="lead">Muestra qué historia histórica y qué evidencias actuales aparecen en cada sección del guion original.</p><div class="story-grid">{_story_map_html(item['stories'])}</div></section>{problem_block}{script_block}</main>
<script>
(() => {{
  const scriptNode = document.getElementById('scriptText');
  const norm = value => String(value || '').toLowerCase();
  const scriptOriginal = scriptNode.textContent;
  const normalizedScript = norm(scriptOriginal);
}})();
</script></body></html>"""
    if not item["script"]:
        return document
    document = apply_script_editor(document, episode_key=f"experiment:{item['id']}")
    return apply_script_productivity(
        document,
        episode_key=f"experiment:{item['id']}",
        original_text=item["script"],
        words_per_second=float(item["words_per_minute"]) / 60.0,
    )


BASE_CSS = r"""
:root{--bg:#080d13;--panel:#0f1822;--line:#243548;--text:#eef6ff;--muted:#8da0b3;--accent:#66d9ff;--ok:#57c49a;--bad:#ff8b8b}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:38px 22px 80px}.eyebrow{display:block;color:var(--accent);font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}h1{font-size:clamp(30px,5vw,56px);margin:7px 0}h2{margin:0 0 14px}h3{margin:5px 0}.lead,.muted{color:var(--muted);line-height:1.6}.back{display:inline-block;margin-bottom:24px;color:var(--accent);text-decoration:none}.toolbar{display:grid;grid-template-columns:minmax(240px,2fr) repeat(3,minmax(130px,1fr));gap:12px;margin:24px 0 10px}.toolbar label{display:grid;gap:7px;color:var(--muted);font-size:13px;font-weight:700}.toolbar input,.toolbar select{width:100%;min-height:44px;margin:0;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#0b121a;color:var(--text);font:inherit}.result-count{margin:12px 0;color:var(--muted);font-size:13px}.grid{display:grid;gap:16px}.experiment-card,.panel,#guion{padding:20px;border:1px solid var(--line);border-radius:16px;background:var(--panel);margin:18px 0}.experiment-card header{display:flex;justify-content:space-between;gap:16px}.status{display:inline-block;height:max-content;padding:6px 9px;border:1px solid #315c70;border-radius:999px;color:var(--accent);font-size:11px}dl{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:18px 0}dl div{padding:10px;background:#0a1119;border-radius:10px}dt{font-size:10px;color:var(--muted)}dd{margin:4px 0 0;font-weight:750}.checks{display:flex;flex-wrap:wrap;gap:7px;padding:0;list-style:none}.checks li{padding:6px 9px;border-radius:8px;background:#0a1119;font-size:12px}.pass{color:var(--ok)}.fail{color:var(--bad)}.button{display:inline-block;border:1px solid #35506b;border-radius:9px;background:#152638;color:#d7ebfa;padding:8px 11px;text-decoration:none;font:inherit}.button.primary{background:#17344a;border-color:#356789;color:#dff5ff}.archive{margin-top:32px;border-top:1px solid var(--line);padding-top:18px}.archive summary{display:flex;align-items:center;justify-content:space-between;gap:16px;cursor:pointer;padding:12px 2px;color:var(--text);font-size:18px;font-weight:800}.archive summary span{color:var(--muted);font-size:13px;font-weight:650}.archive:not([open])>.grid,.archive:not([open])>p{display:none}.story-grid{display:grid;gap:10px}.story-card{border:1px solid var(--line);border-radius:12px;background:#0a1119;padding:14px}.story-kind{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--accent)}code{color:#a8bdd0}.story-card li{margin:10px 0}.story-card li span{color:var(--accent);font-size:11px}.story-card li p{color:var(--muted);margin:4px 0;font-size:12px}.script{max-width:850px;margin:auto;white-space:pre-wrap;line-height:1.68;color:#e4edf5}.empty{color:var(--muted)}[hidden]{display:none!important}@media(max-width:800px){.toolbar{grid-template-columns:1fr 1fr}.search-field{grid-column:1/-1}}@media(max-width:650px){main{padding:24px 14px}.toolbar{grid-template-columns:1fr}.search-field{grid-column:auto}dl{grid-template-columns:repeat(2,1fr)}.experiment-card header{display:block}}
"""


def build_dashboard(*, roots: list[Path], output_dir: Path) -> Path:
    experiments = discover_experiments(roots)
    output_dir.mkdir(parents=True, exist_ok=True)
    public = [{key: value for key, value in item.items() if key != "script"} for item in experiments]
    (output_dir / "experiments.json").write_text(
        json.dumps({"schema_version": 1, "experiments": public}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for item in experiments:
        run_dir = output_dir / "runs" / item["slug"]
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "index.html").write_text(run_document(item), encoding="utf-8")
    index = output_dir / "index.html"
    index.write_text(dashboard_document(experiments), encoding="utf-8")
    return index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the static experiments dashboard")
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(build_dashboard(roots=[Path(root) for root in args.root], output_dir=Path(args.output_dir)))


if __name__ == "__main__":
    main()
