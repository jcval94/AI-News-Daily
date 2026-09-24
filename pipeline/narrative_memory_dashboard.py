from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

from pipeline.narrative_memory import DEFAULT_COOLDOWN_DAYS, load_memory, load_usage_history


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def build_report(
    *,
    memory_path: Path,
    scripts_root: Path,
    as_of: date | None = None,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> dict[str, Any]:
    as_of = as_of or datetime.now(ZoneInfo("America/Mexico_City")).date()
    items, issues = load_memory(memory_path)
    usage = load_usage_history(scripts_root, as_of + timedelta(days=1))

    mechanism_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    source_kind_counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for item in items:
        history = usage.get(item.id, {})
        times_used = int(history.get("times_used", 0) or 0)
        last_used_at = _parse_date(history.get("last_used_at"))
        days_since_use = (as_of - last_used_at).days if last_used_at else None
        cooldown_remaining = (
            max(0, cooldown_days - days_since_use)
            if days_since_use is not None
            else 0
        )
        availability = "cooldown" if cooldown_remaining > 0 else "available"
        quality = round(
            mean(
                [
                    item.surprise_score,
                    item.explanatory_score,
                    item.analogy_potential,
                    item.source_quality_score,
                    item.confidence,
                ]
            ),
            2,
        )

        for mechanism in item.mechanisms:
            mechanism_counts[mechanism] += 1
        for domain in item.domains:
            domain_counts[domain] += 1
        source_kind_counts[item.source_kind] += 1

        rows.append(
            {
                **item.model_dump(),
                "quality_score": quality,
                "times_used": times_used,
                "last_used_at": last_used_at.isoformat() if last_used_at else None,
                "episodes_used": list(history.get("episodes_used", []) or []),
                "cooldown_remaining_days": cooldown_remaining,
                "availability": availability,
                "ready_after": (
                    (last_used_at + timedelta(days=cooldown_days)).isoformat()
                    if cooldown_remaining > 0 and last_used_at
                    else None
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            row["availability"] != "available",
            -float(row["quality_score"]),
            str(row["title"]).casefold(),
        )
    )

    used_count = sum(1 for row in rows if row["times_used"] > 0)
    cooldown_count = sum(1 for row in rows if row["availability"] == "cooldown")
    scheduled_count = source_kind_counts.get("scheduled_research", 0)
    latest_created = max(
        (_parse_date(row.get("created_at")) for row in rows),
        default=None,
        key=lambda value: value or date.min,
    )

    score_fields = (
        "surprise_score",
        "explanatory_score",
        "analogy_potential",
        "visual_score",
        "sourceability_score",
        "source_quality_score",
        "confidence",
    )
    averages = {
        field: _avg([float(row[field]) for row in rows])
        for field in score_fields
    }

    total_mechanism_refs = sum(mechanism_counts.values())
    top_mechanism_count = max(mechanism_counts.values(), default=0)
    concentration = (
        round(top_mechanism_count / total_mechanism_refs, 3)
        if total_mechanism_refs
        else 0.0
    )

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of.isoformat(),
        "cooldown_days": cooldown_days,
        "metrics": {
            "approved_items": len(rows),
            "available_items": len(rows) - cooldown_count,
            "cooldown_items": cooldown_count,
            "used_items": used_count,
            "unused_items": len(rows) - used_count,
            "scheduled_research_items": scheduled_count,
            "editorial_seed_items": source_kind_counts.get("editorial_seed", 0),
            "unique_mechanisms": len(mechanism_counts),
            "unique_domains": len(domain_counts),
            "invalid_or_quarantined_rows": len(issues),
            "latest_created_at": latest_created.isoformat() if latest_created else None,
            "primary_mechanism_concentration": concentration,
            "averages": averages,
        },
        "mechanisms": [
            {"name": name, "count": count}
            for name, count in mechanism_counts.most_common()
        ],
        "domains": [
            {"name": name, "count": count}
            for name, count in domain_counts.most_common()
        ],
        "issues": issues,
        "items": rows,
    }


def _score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def memory_document(report: dict[str, Any]) -> str:
    metrics = report.get("metrics", {}) if isinstance(report.get("metrics"), dict) else {}
    items = report.get("items", []) if isinstance(report.get("items"), list) else []
    mechanisms = report.get("mechanisms", []) if isinstance(report.get("mechanisms"), list) else []
    issues = report.get("issues", []) if isinstance(report.get("issues"), list) else []
    averages = metrics.get("averages", {}) if isinstance(metrics.get("averages"), dict) else {}

    mechanism_options = "".join(
        f'<option value="{_esc(entry.get("name"))}">{_esc(entry.get("name"))} · {_esc(entry.get("count"))}</option>'
        for entry in mechanisms
        if isinstance(entry, dict)
    )
    max_mechanism = max(
        (int(entry.get("count", 0)) for entry in mechanisms if isinstance(entry, dict)),
        default=1,
    )
    mechanism_cards = "".join(
        '<div class="mechanism-row" data-search-item>'
        f'<div><strong>{_esc(entry.get("name"))}</strong><span>{_esc(entry.get("count"))} caso(s)</span></div>'
        f'<div class="bar"><i style="width:{max(8, round(int(entry.get("count", 0)) / max_mechanism * 100))}%"></i></div>'
        '</div>'
        for entry in mechanisms
        if isinstance(entry, dict)
    )

    cards: list[str] = []
    usage_rows: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mechanisms_text = " ".join(str(v) for v in item.get("mechanisms", []))
        domains_text = " ".join(str(v) for v in item.get("domains", []))
        status = str(item.get("availability") or "available")
        status_label = "EN COOLDOWN" if status == "cooldown" else "DISPONIBLE"
        use_text = (
            f'{int(item.get("times_used", 0))} uso(s)'
            if int(item.get("times_used", 0) or 0)
            else "Sin uso"
        )
        cooldown_note = (
            f'Disponible en {int(item.get("cooldown_remaining_days", 0))} d · {_esc(item.get("ready_after"))}'
            if status == "cooldown"
            else "Elegible para retrieval"
        )
        mechanism_chips = "".join(
            f'<span class="chip mechanism">{_esc(value)}</span>'
            for value in item.get("mechanisms", [])
        )
        domain_chips = "".join(
            f'<span class="chip">{_esc(value)}</span>'
            for value in item.get("domains", [])
        )
        sources = "".join(
            f'<a href="{html.escape(str(url), quote=True)}" target="_blank" rel="noopener">fuente {idx}</a>'
            for idx, url in enumerate(item.get("sources", []), 1)
        )
        cards.append(
            '<article class="memory-card" data-memory-card '
            f'data-availability="{_esc(status)}" data-mechanisms="{_esc(mechanisms_text)}" '
            f'data-search="{_esc((str(item.get("title") or "") + " " + mechanisms_text + " " + domains_text).casefold())}">'
            '<div class="card-top">'
            f'<span class="availability {status}">{status_label}</span>'
            f'<span class="quality">Q {_score(item.get("quality_score"))}</span>'
            '</div>'
            f'<h3>{_esc(item.get("title"))}</h3>'
            f'<p class="one-liner">{_esc(item.get("one_liner"))}</p>'
            '<div class="chips">' + mechanism_chips + domain_chips + '</div>'
            '<div class="score-grid">'
            f'<span><b>{_score(item.get("surprise_score"))}</b>Sorpresa</span>'
            f'<span><b>{_score(item.get("explanatory_score"))}</b>Explica</span>'
            f'<span><b>{_score(item.get("analogy_potential"))}</b>Analogía</span>'
            f'<span><b>{_score(item.get("source_quality_score"))}</b>Fuentes</span>'
            '</div>'
            '<div class="card-meta">'
            f'<span>{_esc(use_text)}</span><span>{_esc(cooldown_note)}</span>'
            f'<span>{_esc(item.get("period"))}</span><span>{_esc(item.get("location"))}</span>'
            '</div>'
            '<details><summary>Contrato factual y analogía</summary>'
            f'<p><strong>Mapping:</strong> {_esc(item.get("analogy_mapping"))}</p>'
            f'<p><strong>Límite:</strong> {_esc(item.get("analogy_limits"))}</p>'
            f'<p><strong>Claims verificados:</strong> {_esc(" · ".join(str(v) for v in item.get("verified_claims", [])))}</p>'
            f'<p><strong>Incertidumbres:</strong> {_esc(" · ".join(str(v) for v in item.get("uncertainties", [])))}</p>'
            f'<div class="sources">{sources}</div>'
            '</details>'
            '</article>'
        )
        if int(item.get("times_used", 0) or 0) > 0:
            episodes = ", ".join(str(value) for value in item.get("episodes_used", []))
            usage_rows.append(
                '<tr data-search-item>'
                f'<td>{_esc(item.get("title"))}</td>'
                f'<td>{_esc(item.get("times_used"))}</td>'
                f'<td>{_esc(item.get("last_used_at"))}</td>'
                f'<td>{_esc(episodes)}</td>'
                '</tr>'
            )

    issues_block = (
        '<div class="warning"><strong>Filas fuera del contrato</strong><ul>'
        + "".join(f'<li>{_esc(issue)}</li>' for issue in issues)
        + '</ul></div>'
        if issues
        else '<div class="ok-note">Todas las filas leídas cumplen el contrato productivo.</div>'
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Narrative Memory · AI News Daily</title>
<style>
:root{{--bg:#080d13;--panel:#0e1620;--panel2:#111d29;--line:#223247;--text:#edf6ff;--muted:#8799aa;--accent:#6edaff;--ok:#5bd0a3;--warn:#f2be62;--cool:#aa8cff}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:radial-gradient(circle at 20% 0,#102638 0,transparent 34%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1500px;margin:auto;padding:34px 30px 70px}}.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:850}}
.hero{{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,.8fr);gap:28px;align-items:end;margin-bottom:22px}}h1{{font-size:clamp(34px,5vw,66px);line-height:.96;margin:8px 0 14px;letter-spacing:-.045em}}.hero p{{max-width:820px;color:#a9bac9;font-size:15px;line-height:1.65;margin:0}}.freshness{{background:#0d1924;border:1px solid var(--line);border-radius:16px;padding:17px}}.freshness strong{{display:block;font-size:20px;margin-top:4px}}
.kpis{{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;margin:22px 0}}.kpi{{background:linear-gradient(180deg,#111c28,#0c141d);border:1px solid var(--line);border-radius:15px;padding:15px}}.kpi span{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em}}.kpi b{{display:block;font-size:28px;margin-top:5px;letter-spacing:-.03em}}.kpi small{{color:#8ea2b5;font-size:10px}}
.toolbar{{position:sticky;top:0;z-index:5;display:grid;grid-template-columns:minmax(240px,1fr) 220px 180px;gap:9px;padding:11px 0;background:linear-gradient(180deg,#080d13 75%,transparent)}}input,select{{width:100%;background:#0c151f;color:var(--text);border:1px solid var(--line);border-radius:11px;padding:11px 12px;outline:none}}input:focus,select:focus{{border-color:#4c9ec0;box-shadow:0 0 0 3px #17405a55}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.memory-card{{background:linear-gradient(180deg,#111c27,#0d151e);border:1px solid var(--line);border-radius:17px;padding:18px;min-width:0}}.memory-card[hidden]{{display:none}}.card-top{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.availability{{font-size:9px;font-weight:900;letter-spacing:.1em;border-radius:999px;padding:5px 8px;border:1px solid}}.availability.available{{color:var(--ok);border-color:#28644f;background:#10271f}}.availability.cooldown{{color:var(--cool);border-color:#574985;background:#1c1830}}.quality{{font-size:11px;color:#b7ddec;font-variant-numeric:tabular-nums}}.memory-card h3{{font-size:19px;margin:11px 0 6px}}.one-liner{{margin:0;color:#a9bac9;line-height:1.5;font-size:13px}}
.chips{{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0}}.chip{{font-size:9px;border:1px solid #304153;background:#111b25;color:#aabaca;border-radius:999px;padding:4px 7px}}.chip.mechanism{{border-color:#29546c;color:#8edfff;background:#10202b}}
.score-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:13px 0}}.score-grid span{{display:grid;gap:1px;background:#09121a;border:1px solid #1d2c3d;border-radius:10px;padding:9px;color:var(--muted);font-size:9px}}.score-grid b{{font-size:17px;color:var(--text)}}.card-meta{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;color:#8497a9;font-size:10px;margin-bottom:8px}}details{{border-top:1px solid #1d2c3b;padding-top:10px}}summary{{cursor:pointer;color:#9adcf4;font-size:11px;font-weight:750}}details p{{color:#9dafbd;line-height:1.55;font-size:11px}}.sources{{display:flex;gap:7px;flex-wrap:wrap}}.sources a{{color:var(--accent);font-size:10px}}
.section-grid{{display:grid;grid-template-columns:minmax(320px,.8fr) minmax(0,1.2fr);gap:14px;margin:28px 0}}.panel{{background:#0d151e;border:1px solid var(--line);border-radius:17px;padding:18px}}.panel h2{{font-size:19px;margin:4px 0 15px}}.mechanism-row{{display:grid;grid-template-columns:minmax(190px,1fr) minmax(100px,.65fr);gap:12px;align-items:center;margin:8px 0}}.mechanism-row>div:first-child{{display:flex;justify-content:space-between;gap:9px;font-size:10px}}.mechanism-row span{{color:var(--muted)}}.bar{{height:7px;background:#091018;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,#3288ac,#6edaff);border-radius:99px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{text-align:left;padding:9px 7px;border-bottom:1px solid #1c2a39;vertical-align:top}}th{{color:#8ca0b3;font-size:9px;text-transform:uppercase;letter-spacing:.08em}}.empty{{color:var(--muted);font-size:12px}}.warning,.ok-note{{margin-top:18px;border-radius:13px;padding:13px;font-size:11px;line-height:1.5}}.warning{{border:1px solid #6c5325;background:#261d0d;color:#e9c87e}}.ok-note{{border:1px solid #255744;background:#10251d;color:#84d9b8}}
.footer-note{{margin-top:24px;color:#718597;font-size:10px}}@media(max-width:1000px){{.hero{{grid-template-columns:1fr}}.kpis{{grid-template-columns:repeat(3,1fr)}}.grid,.section-grid{{grid-template-columns:1fr}}}}@media(max-width:680px){{main{{padding:22px 14px 50px}}.kpis{{grid-template-columns:repeat(2,1fr)}}.toolbar{{grid-template-columns:1fr;position:static}}.score-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body data-memory-page="narrative-memory">
<main>
<section class="hero">
<div><span class="eyebrow">Narrative Memory · observabilidad editorial</span><h1>¿Qué historias tiene el sistema para pensar mejor?</h1><p>Biblioteca verificada de paralelos narrativos. Esta vista separa inventario de uso real: muestra qué mecanismos están cubiertos, qué casos siguen disponibles, cuáles están en cooldown y qué paralelos llegaron efectivamente a episodios aprobados.</p></div>
<div class="freshness"><span class="eyebrow">Snapshot</span><strong>{_esc(report.get("as_of_date"))}</strong><small>Última alta: {_esc(metrics.get("latest_created_at"))} · cooldown {int(report.get("cooldown_days", 0))} días</small></div>
</section>
<section class="kpis">
<div class="kpi"><span>Biblioteca</span><b>{_esc(metrics.get("approved_items"))}</b><small>casos aprobados</small></div>
<div class="kpi"><span>Disponibles</span><b>{_esc(metrics.get("available_items"))}</b><small>elegibles hoy</small></div>
<div class="kpi"><span>En cooldown</span><b>{_esc(metrics.get("cooldown_items"))}</b><small>anti-repetición</small></div>
<div class="kpi"><span>Usados</span><b>{_esc(metrics.get("used_items"))}</b><small>en episodios aprobados</small></div>
<div class="kpi"><span>Mecanismos</span><b>{_esc(metrics.get("unique_mechanisms"))}</b><small>estructuras distintas</small></div>
<div class="kpi"><span>Calidad media</span><b>{_score(averages.get("source_quality_score"))}</b><small>fuentes / 10</small></div>
</section>
<div class="toolbar">
<input id="memorySearch" type="search" placeholder="Buscar caso, dominio o mecanismo…" aria-label="Buscar Narrative Memory">
<select id="mechanismFilter" aria-label="Filtrar mecanismo"><option value="">Todos los mecanismos</option>{mechanism_options}</select>
<select id="availabilityFilter" aria-label="Filtrar disponibilidad"><option value="">Toda disponibilidad</option><option value="available">Disponibles</option><option value="cooldown">Cooldown</option></select>
</div>
<section id="memoryGrid" class="grid">{"".join(cards)}</section>
<div id="emptyMemory" class="empty" hidden>No hay casos que coincidan con los filtros.</div>
<section class="section-grid">
<div class="panel"><span class="eyebrow">Cobertura</span><h2>Mecanismos narrativos</h2>{mechanism_cards or '<p class="empty">Sin mecanismos disponibles.</p>'}<p class="footer-note">Concentración del mecanismo más frecuente: {_esc(metrics.get("primary_mechanism_concentration"))}. Un valor alto puede indicar que la biblioteca está acumulando variaciones de la misma idea.</p></div>
<div class="panel"><span class="eyebrow">Uso real</span><h2>Paralelos que llegaron a episodios aprobados</h2><table><thead><tr><th>Caso</th><th>Usos</th><th>Último uso</th><th>Episodios</th></tr></thead><tbody>{"".join(usage_rows) if usage_rows else '<tr><td colspan="4" class="empty">Aún no hay usos aprobados registrados.</td></tr>'}</tbody></table></div>
</section>
{issues_block}
<p class="footer-note">La biblioteca es contexto verificado, no autoridad editorial. El Director puede elegir 0–2 casos recuperados y el Writer recibe solo esos registros. Un episodio rechazado no cuenta como uso.</p>
</main>
<script>
const cards=[...document.querySelectorAll('[data-memory-card]')];
const search=document.getElementById('memorySearch');
const mechanism=document.getElementById('mechanismFilter');
const availability=document.getElementById('availabilityFilter');
const empty=document.getElementById('emptyMemory');
function applyFilters(){{
  const q=(search.value||'').trim().toLocaleLowerCase('es');
  const m=(mechanism.value||'').toLocaleLowerCase('es');
  const a=availability.value||'';
  let visible=0;
  cards.forEach(card=>{{
    const text=(card.dataset.search||'').toLocaleLowerCase('es');
    const mechanisms=(card.dataset.mechanisms||'').toLocaleLowerCase('es');
    const hit=(!q||text.includes(q))&&(!m||mechanisms.split(' ').includes(m))&&(!a||card.dataset.availability===a);
    card.hidden=!hit;
    if(hit) visible+=1;
  }});
  empty.hidden=visible!==0;
}}
[search,mechanism,availability].forEach(el=>el&&el.addEventListener(el===search?'input':'change',applyFilters));
</script>
</body>
</html>
"""


def build_dashboard(
    *,
    memory_path: Path,
    scripts_root: Path,
    output_dir: Path,
    as_of: date | None = None,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> Path:
    report = build_report(
        memory_path=memory_path,
        scripts_root=scripts_root,
        as_of=as_of,
        cooldown_days=cooldown_days,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "narrative-memory.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    index = output_dir / "index.html"
    index.write_text(memory_document(report), encoding="utf-8")
    return index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Narrative Memory observability for GitHub Pages")
    parser.add_argument("--memory", default="editorial/narrative_memory.jsonl")
    parser.add_argument("--scripts-root", default="scripts")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--cooldown-days", type=int, default=DEFAULT_COOLDOWN_DAYS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    result = build_dashboard(
        memory_path=Path(args.memory),
        scripts_root=Path(args.scripts_root),
        output_dir=Path(args.output_dir),
        as_of=as_of,
        cooldown_days=args.cooldown_days,
    )
    print(result)


if __name__ == "__main__":
    main()
