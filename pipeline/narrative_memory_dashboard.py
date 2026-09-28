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
            -((_parse_date(row.get("created_at")) or date.min).toordinal()),
            -float(row.get("surprise_score", 0) or 0),
            -float(row["quality_score"]),
            row["availability"] != "available",
            str(row["title"]).casefold(),
        )
    )

    used_count = sum(1 for row in rows if row["times_used"] > 0)
    cooldown_count = sum(1 for row in rows if row["availability"] == "cooldown")
    episode_usage_map: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        for episode in row.get("episodes_used", []):
            episode_usage_map.setdefault(str(episode), []).append(
                {"id": str(row["id"]), "title": str(row["title"])}
            )
    episode_usage = [
        {"episode": episode, "parallels": parallels}
        for episode, parallels in sorted(episode_usage_map.items(), reverse=True)
    ]
    scheduled_count = source_kind_counts.get("scheduled_research", 0)
    latest_created = max(
        (_parse_date(row.get("created_at")) for row in rows),
        default=None,
        key=lambda value: value or date.min,
    )

    daily_update_map: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        created_at = str(row.get("created_at") or "").strip()
        if created_at:
            daily_update_map.setdefault(created_at, []).append(row)
    daily_updates = [
        {
            "date": created_at,
            "count": len(batch),
            "scheduled_research_count": sum(
                1 for item in batch if item.get("source_kind") == "scheduled_research"
            ),
            "average_surprise": _avg(
                [float(item.get("surprise_score", 0) or 0) for item in batch]
            ),
            "items": sorted(
                batch,
                key=lambda item: (
                    -float(item.get("surprise_score", 0) or 0),
                    -float(item.get("quality_score", 0) or 0),
                    str(item.get("title") or "").casefold(),
                ),
            ),
        }
        for created_at, batch in sorted(daily_update_map.items(), reverse=True)
    ]

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
            "average_quality_score": _avg([float(row["quality_score"]) for row in rows]),
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
        "episode_usage": episode_usage,
        "daily_updates": daily_updates,
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
    domains = report.get("domains", []) if isinstance(report.get("domains"), list) else []
    issues = report.get("issues", []) if isinstance(report.get("issues"), list) else []
    episode_usage = report.get("episode_usage", []) if isinstance(report.get("episode_usage"), list) else []
    daily_updates = report.get("daily_updates", []) if isinstance(report.get("daily_updates"), list) else []
    averages = metrics.get("averages", {}) if isinstance(metrics.get("averages"), dict) else {}

    mechanism_options = "".join(
        f'<option value="{_esc(entry.get("name"))}">{_esc(entry.get("name"))} · {_esc(entry.get("count"))}</option>'
        for entry in mechanisms
        if isinstance(entry, dict)
    )
    domain_options = "".join(
        f'<option value="{_esc(entry.get("name"))}">{_esc(entry.get("name"))} · {_esc(entry.get("count"))}</option>'
        for entry in domains
        if isinstance(entry, dict)
    )
    source_kind_options = "".join(
        f'<option value="{_esc(source_kind)}">{_esc(source_kind.replace("_", " ").title())}</option>'
        for source_kind in sorted(
            {
                str(item.get("source_kind"))
                for item in items
                if isinstance(item, dict) and item.get("source_kind")
            }
        )
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
            f'data-domains="{_esc(domains_text)}" data-source-kind="{_esc(item.get("source_kind"))}" '
            f'data-surprise="{_esc(item.get("surprise_score"))}" data-quality="{_esc(item.get("quality_score"))}" '
            f'data-created-at="{_esc(item.get("created_at"))}" data-times-used="{_esc(item.get("times_used", 0))}" '
            f'data-search="{_esc((str(item.get("title") or "") + " " + mechanisms_text + " " + domains_text + " " + str(item.get("source_kind") or "")).casefold())}">'
            '<div class="card-top">'
            f'<span class="availability {status}">{status_label}</span>'
            '<span class="card-freshness">'
            f'<span>{_esc(item.get("created_at"))}</span>'
            f'<span class="quality">Q {_score(item.get("quality_score"))}</span>'
            '</span>'
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
    episode_rows = "".join(
        '<tr data-search-item>'
        f'<td>{_esc(entry.get("episode"))}</td>'
        f'<td>{_esc(" · ".join(str(item.get("title") or item.get("id")) for item in entry.get("parallels", [])))}</td>'
        f'<td>{_esc(len(entry.get("parallels", [])))}</td>'
        '</tr>'
        for entry in episode_usage
        if isinstance(entry, dict)
    )

    update_sections: list[str] = []
    for batch in daily_updates:
        if not isinstance(batch, dict):
            continue
        update_items = []
        for item in batch.get("items", []):
            if not isinstance(item, dict):
                continue
            origin = str(item.get("source_kind") or "unknown").replace("_", " ")
            update_items.append(
                '<article class="update-card">'
                '<div class="update-card-top">'
                f'<span class="update-origin">{_esc(origin)}</span>'
                f'<span class="update-surprise">Sorpresa {_score(item.get("surprise_score"))}</span>'
                '</div>'
                f'<h3>{_esc(item.get("title"))}</h3>'
                f'<p>{_esc(item.get("one_liner"))}</p>'
                '<div class="update-meta">'
                f'<span>Q {_score(item.get("quality_score"))}</span>'
                f'<span>{_esc(" · ".join(str(v) for v in item.get("domains", [])))}</span>'
                f'<span>{_esc(" · ".join(str(v) for v in item.get("mechanisms", [])))}</span>'
                '</div>'
                '</article>'
            )
        update_sections.append(
            '<section class="update-day">'
            '<div class="update-day-head">'
            f'<div><span class="eyebrow">Alta diaria</span><h2>{_esc(batch.get("date"))}</h2></div>'
            '<div class="update-day-stats">'
            f'<span><b>{_esc(batch.get("count"))}</b> altas</span>'
            f'<span><b>{_esc(batch.get("scheduled_research_count"))}</b> research</span>'
            f'<span><b>{_score(batch.get("average_surprise"))}</b> sorpresa media</span>'
            '</div>'
            '</div>'
            f'<div class="update-grid">{"".join(update_items)}</div>'
            '</section>'
        )
    updates_html = "".join(update_sections) or '<p class="empty">Aún no hay altas fechadas en Narrative Memory.</p>'

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
.tabs{{display:flex;gap:7px;flex-wrap:wrap;margin:18px 0 6px;padding:5px;background:#0b131c;border:1px solid var(--line);border-radius:14px;width:max-content;max-width:100%}}.tab-button{{appearance:none;border:0;background:transparent;color:#8fa3b5;border-radius:10px;padding:9px 12px;font:inherit;font-size:11px;font-weight:800;cursor:pointer}}.tab-button.active{{background:#152433;color:var(--text);box-shadow:inset 0 0 0 1px #294057}}.tab-panel[hidden]{{display:none}}
.toolbar{{position:sticky;top:0;z-index:5;display:grid;grid-template-columns:minmax(220px,1.5fr) repeat(6,minmax(145px,.7fr));gap:9px;padding:11px 0;background:linear-gradient(180deg,#080d13 75%,transparent)}}input,select{{width:100%;background:#0c151f;color:var(--text);border:1px solid var(--line);border-radius:11px;padding:11px 12px;outline:none}}input:focus,select:focus{{border-color:#4c9ec0;box-shadow:0 0 0 3px #17405a55}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.memory-card{{background:linear-gradient(180deg,#111c27,#0d151e);border:1px solid var(--line);border-radius:17px;padding:18px;min-width:0}}.memory-card[hidden]{{display:none}}.card-top{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.card-freshness{{display:flex;align-items:center;gap:8px;color:#7f93a5;font-size:10px}}.availability{{font-size:9px;font-weight:900;letter-spacing:.1em;border-radius:999px;padding:5px 8px;border:1px solid}}.availability.available{{color:var(--ok);border-color:#28644f;background:#10271f}}.availability.cooldown{{color:var(--cool);border-color:#574985;background:#1c1830}}.quality{{font-size:11px;color:#b7ddec;font-variant-numeric:tabular-nums}}.memory-card h3{{font-size:19px;margin:11px 0 6px}}.one-liner{{margin:0;color:#a9bac9;line-height:1.5;font-size:13px}}
.chips{{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0}}.chip{{font-size:9px;border:1px solid #304153;background:#111b25;color:#aabaca;border-radius:999px;padding:4px 7px}}.chip.mechanism{{border-color:#29546c;color:#8edfff;background:#10202b}}
.score-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:13px 0}}.score-grid span{{display:grid;gap:1px;background:#09121a;border:1px solid #1d2c3d;border-radius:10px;padding:9px;color:var(--muted);font-size:9px}}.score-grid b{{font-size:17px;color:var(--text)}}.card-meta{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;color:#8497a9;font-size:10px;margin-bottom:8px}}details{{border-top:1px solid #1d2c3b;padding-top:10px}}summary{{cursor:pointer;color:#9adcf4;font-size:11px;font-weight:750}}details p{{color:#9dafbd;line-height:1.55;font-size:11px}}.sources{{display:flex;gap:7px;flex-wrap:wrap}}.sources a{{color:var(--accent);font-size:10px}}
.section-grid{{display:grid;grid-template-columns:minmax(320px,.8fr) minmax(0,1.2fr);gap:14px;margin:28px 0}}.panel{{background:#0d151e;border:1px solid var(--line);border-radius:17px;padding:18px}}.panel h2{{font-size:19px;margin:4px 0 15px}}.mechanism-row{{display:grid;grid-template-columns:minmax(190px,1fr) minmax(100px,.65fr);gap:12px;align-items:center;margin:8px 0}}.mechanism-row>div:first-child{{display:flex;justify-content:space-between;gap:9px;font-size:10px}}.mechanism-row span{{color:var(--muted)}}.bar{{height:7px;background:#091018;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,#3288ac,#6edaff);border-radius:99px}}
table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{text-align:left;padding:9px 7px;border-bottom:1px solid #1c2a39;vertical-align:top}}th{{color:#8ca0b3;font-size:9px;text-transform:uppercase;letter-spacing:.08em}}.empty{{color:var(--muted);font-size:12px}}.warning,.ok-note{{margin-top:18px;border-radius:13px;padding:13px;font-size:11px;line-height:1.5}}.warning{{border:1px solid #6c5325;background:#261d0d;color:#e9c87e}}.ok-note{{border:1px solid #255744;background:#10251d;color:#84d9b8}}
.update-day{{margin:18px 0 28px}}.update-day-head{{display:flex;align-items:end;justify-content:space-between;gap:18px;margin-bottom:12px}}.update-day-head h2{{margin:3px 0 0;font-size:24px}}.update-day-stats{{display:flex;gap:8px;flex-wrap:wrap}}.update-day-stats span{{display:grid;gap:1px;min-width:92px;background:#0c151f;border:1px solid var(--line);border-radius:10px;padding:8px 10px;color:var(--muted);font-size:9px}}.update-day-stats b{{font-size:15px;color:var(--text)}}.update-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.update-card{{background:linear-gradient(180deg,#111c27,#0d151e);border:1px solid var(--line);border-radius:15px;padding:15px}}.update-card-top{{display:flex;justify-content:space-between;gap:8px;align-items:center}}.update-origin{{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent)}}.update-surprise{{font-size:10px;color:#f2d28b}}.update-card h3{{font-size:16px;margin:9px 0 6px}}.update-card p{{font-size:11px;line-height:1.5;color:#9dafbd;margin:0}}.update-meta{{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}}.update-meta span{{font-size:9px;color:#8397a9;border:1px solid #263748;border-radius:999px;padding:4px 7px}}
.footer-note{{margin-top:24px;color:#718597;font-size:10px}}@media(max-width:1180px){{.toolbar{{grid-template-columns:repeat(3,minmax(0,1fr))}}.update-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:1000px){{.hero{{grid-template-columns:1fr}}.kpis{{grid-template-columns:repeat(3,1fr)}}.grid,.section-grid{{grid-template-columns:1fr}}}}@media(max-width:680px){{main{{padding:22px 14px 50px}}.kpis{{grid-template-columns:repeat(2,1fr)}}.toolbar{{grid-template-columns:1fr;position:static}}.score-grid{{grid-template-columns:repeat(2,1fr)}}.update-grid{{grid-template-columns:1fr}}.update-day-head{{align-items:flex-start;flex-direction:column}}}}
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
<div class="kpi"><span>Sin cooldown</span><b>{_esc(metrics.get("available_items"))}</b><small>preferidos hoy</small></div>
<div class="kpi"><span>En cooldown</span><b>{_esc(metrics.get("cooldown_items"))}</b><small>anti-repetición</small></div>
<div class="kpi"><span>Usados</span><b>{_esc(metrics.get("used_items"))}</b><small>en episodios aprobados</small></div>
<div class="kpi"><span>Mecanismos</span><b>{_esc(metrics.get("unique_mechanisms"))}</b><small>estructuras distintas</small></div>
<div class="kpi"><span>Calidad media</span><b>{_score(metrics.get("average_quality_score"))}</b><small>score compuesto / 10</small></div>
</section>
<nav class="tabs" aria-label="Secciones de Editorial Memory">
<button class="tab-button active" type="button" data-memory-tab="library">Explorar memoria</button>
<button class="tab-button" type="button" data-memory-tab="updates">Actualizaciones diarias</button>
<button class="tab-button" type="button" data-memory-tab="coverage">Cobertura &amp; uso</button>
</nav>
<section class="tab-panel" data-memory-panel="library">
<div class="toolbar">
<input id="memorySearch" type="search" placeholder="Buscar caso, dominio, mecanismo u origen…" aria-label="Buscar Narrative Memory">
<select id="mechanismFilter" aria-label="Filtrar mecanismo"><option value="">Todos los mecanismos</option>{mechanism_options}</select>
<select id="domainFilter" aria-label="Filtrar dominio"><option value="">Todos los dominios</option>{domain_options}</select>
<select id="sourceKindFilter" aria-label="Filtrar origen"><option value="">Todos los orígenes</option>{source_kind_options}</select>
<select id="availabilityFilter" aria-label="Filtrar disponibilidad"><option value="">Toda disponibilidad</option><option value="available">Disponibles</option><option value="cooldown">Cooldown</option></select>
<select id="surpriseFilter" aria-label="Filtrar sorpresa"><option value="0">Toda sorpresa</option><option value="9">Sorpresa ≥ 9.0</option><option value="8.5">Sorpresa ≥ 8.5</option><option value="8">Sorpresa ≥ 8.0</option></select>
<select id="memorySort" aria-label="Ordenar memoria"><option value="recent-surprise">Reciente + sorpresa</option><option value="surprise">Mayor sorpresa</option><option value="quality">Mayor calidad</option><option value="available">Disponibles primero</option></select>
</div>
<section id="memoryGrid" class="grid">{"".join(cards)}</section>
<div id="emptyMemory" class="empty" hidden>No hay casos que coincidan con los filtros.</div>
</section>
<section class="tab-panel" data-memory-panel="updates" hidden>
<div class="panel" style="margin:12px 0 18px"><span class="eyebrow">Feed de altas</span><h2>Qué cambió cada día</h2><p class="one-liner">Nuevos registros agrupados por <code>created_at</code>, con investigación programada y semillas editoriales visibles por separado. Dentro de cada día se prioriza sorpresa y calidad.</p></div>
{updates_html}
</section>
<section class="tab-panel" data-memory-panel="coverage" hidden>
<section class="section-grid">
<div class="panel"><span class="eyebrow">Cobertura</span><h2>Mecanismos narrativos</h2>{mechanism_cards or '<p class="empty">Sin mecanismos disponibles.</p>'}<p class="footer-note">Concentración del mecanismo más frecuente: {_esc(metrics.get("primary_mechanism_concentration"))}. Un valor alto puede indicar que la biblioteca está acumulando variaciones de la misma idea.</p></div>
<div class="panel"><span class="eyebrow">Uso real</span><h2>Qué paralelos utilizó cada episodio</h2><table><thead><tr><th>Episodio</th><th>Paralelos</th><th>Total</th></tr></thead><tbody>{episode_rows if episode_rows else '<tr><td colspan="3" class="empty">Aún no hay usos aprobados registrados.</td></tr>'}</tbody></table></div>
</section>
{issues_block}
</section>
<p class="footer-note">La biblioteca es contexto verificado, no autoridad factual sobre noticias actuales. El Director debe elegir 1–2 casos recuperados; uno debe ser el gancho de apertura y el Writer recibe solo esos registros. Un episodio rechazado no cuenta como uso. La vista principal prioriza fecha de alta y sorpresa; los controles permiten cambiar el orden sin alterar el contrato productivo.</p>
</main>
<script>
const cards=[...document.querySelectorAll('[data-memory-card]')];
const grid=document.getElementById('memoryGrid');
const search=document.getElementById('memorySearch');
const mechanism=document.getElementById('mechanismFilter');
const domain=document.getElementById('domainFilter');
const sourceKind=document.getElementById('sourceKindFilter');
const availability=document.getElementById('availabilityFilter');
const surprise=document.getElementById('surpriseFilter');
const sort=document.getElementById('memorySort');
const empty=document.getElementById('emptyMemory');
const norm=value=>(value||'').toLocaleLowerCase('es');
function sortCards(){{
  const mode=sort?.value||'recent-surprise';
  const sorted=[...cards].sort((left,right)=>{{
    const dateDiff=norm(right.dataset.createdAt).localeCompare(norm(left.dataset.createdAt));
    const surpriseDiff=(Number(right.dataset.surprise)||0)-(Number(left.dataset.surprise)||0);
    const qualityDiff=(Number(right.dataset.quality)||0)-(Number(left.dataset.quality)||0);
    if(mode==='surprise') return surpriseDiff||dateDiff||qualityDiff;
    if(mode==='quality') return qualityDiff||dateDiff||surpriseDiff;
    if(mode==='available'){{
      const availabilityDiff=(left.dataset.availability==='available'?0:1)-(right.dataset.availability==='available'?0:1);
      return availabilityDiff||dateDiff||surpriseDiff||qualityDiff;
    }}
    return dateDiff||surpriseDiff||qualityDiff;
  }});
  sorted.forEach(card=>grid.appendChild(card));
}}
function applyFilters(){{
  const q=norm(search?.value).trim();
  const m=norm(mechanism?.value);
  const d=norm(domain?.value);
  const sk=norm(sourceKind?.value);
  const a=availability?.value||'';
  const minSurprise=Number(surprise?.value||0);
  let visible=0;
  cards.forEach(card=>{{
    const text=norm(card.dataset.search);
    const mechanisms=norm(card.dataset.mechanisms);
    const domains=norm(card.dataset.domains);
    const origin=norm(card.dataset.sourceKind);
    const score=Number(card.dataset.surprise)||0;
    const hit=(!q||text.includes(q))
      &&(!m||mechanisms.split(' ').includes(m))
      &&(!d||domains.includes(d))
      &&(!sk||origin===sk)
      &&(!a||card.dataset.availability===a)
      &&score>=minSurprise;
    card.hidden=!hit;
    if(hit) visible+=1;
  }});
  sortCards();
  empty.hidden=visible!==0;
}}
[search,mechanism,domain,sourceKind,availability,surprise,sort].forEach(el=>el&&el.addEventListener(el===search?'input':'change',applyFilters));
document.querySelectorAll('[data-memory-tab]').forEach(button=>button.addEventListener('click',()=>{{
  const target=button.dataset.memoryTab;
  document.querySelectorAll('[data-memory-tab]').forEach(item=>item.classList.toggle('active',item===button));
  document.querySelectorAll('[data-memory-panel]').forEach(panel=>panel.hidden=panel.dataset.memoryPanel!==target);
}}));
applyFilters();
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
