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
from pipeline.news import parse_news_file


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
    news_root: Path | None = None,
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

    news_batches: list[dict[str, Any]] = []
    news_issues: list[str] = []
    news_category_counts: Counter[str] = Counter()
    if news_root is not None and news_root.is_dir():
        for news_path in sorted(
            news_root.glob("*.txt"),
            key=lambda path: path.name,
            reverse=True,
        ):
            try:
                parsed_news = parse_news_file(news_path)
            except (OSError, ValueError) as exc:
                news_issues.append(f"{news_path.name}: {exc}")
                continue
            if not parsed_news:
                continue
            serialized: list[dict[str, Any]] = []
            for news_item in parsed_news:
                payload = news_item.model_dump(exclude={"raw_content"})
                category = str(payload.get("category") or "sin categoría")
                news_category_counts[category] += 1
                serialized.append(payload)
            news_batches.append(
                {
                    "source_file": news_path.name,
                    "deposit_key": news_path.stem,
                    "date": str(serialized[0].get("date") or ""),
                    "count": len(serialized),
                    "categories": sorted(
                        {str(item.get("category") or "sin categoría") for item in serialized}
                    ),
                    "items": serialized,
                }
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
        "news": {
            "batch_count": len(news_batches),
            "item_count": sum(int(batch["count"]) for batch in news_batches),
            "latest_source_file": news_batches[0]["source_file"] if news_batches else None,
            "categories": [
                {"name": name, "count": count}
                for name, count in news_category_counts.most_common()
            ],
            "issues": news_issues,
            "batches": news_batches,
        },
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
    news = report.get("news", {}) if isinstance(report.get("news"), dict) else {}
    news_batches = news.get("batches", []) if isinstance(news.get("batches"), list) else []
    news_categories = news.get("categories", []) if isinstance(news.get("categories"), list) else []
    averages = metrics.get("averages", {}) if isinstance(metrics.get("averages"), dict) else {}

    news_category_buttons = "".join(
        f'<button type="button" class="filter-chip news-chip" data-news-category="{_esc(entry.get("name"))}">{_esc(entry.get("name"))} <span>{_esc(entry.get("count"))}</span></button>'
        for entry in news_categories
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

    news_sections: list[str] = []
    for batch in news_batches:
        if not isinstance(batch, dict):
            continue
        news_cards: list[str] = []
        for item in batch.get("items", []):
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "sin categoría")
            search_text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("source") or ""),
                    category,
                    str(item.get("summary") or ""),
                    str(item.get("why_it_matters") or ""),
                ]
            ).casefold()
            link = str(item.get("url") or "").strip()
            link_html = (
                f'<a class="news-link" href="{html.escape(link, quote=True)}" target="_blank" rel="noopener">Abrir fuente ↗</a>'
                if link
                else '<span class="news-link muted-link">Sin enlace</span>'
            )
            news_cards.append(
                '<article class="news-card" data-news-card '
                f'data-category="{_esc(category)}" data-search="{_esc(search_text)}">'
                '<div class="news-card-top">'
                f'<span class="news-category">{_esc(category)}</span>'
                f'<span class="news-source">{_esc(item.get("source"))}</span>'
                '</div>'
                f'<h3>{_esc(item.get("title"))}</h3>'
                f'<p>{_esc(item.get("summary"))}</p>'
                '<details><summary>Por qué importa</summary>'
                f'<p>{_esc(item.get("why_it_matters"))}</p>'
                '</details>'
                f'{link_html}'
                '</article>'
            )
        news_sections.append(
            '<section class="news-batch" data-news-batch '
            f'data-deposit-key="{_esc(batch.get("deposit_key"))}">'
            '<div class="news-batch-head">'
            '<div>'
            '<span class="eyebrow">Depósito en news/</span>'
            f'<h2>{_esc(batch.get("date"))}</h2>'
            f'<code>{_esc(batch.get("source_file"))}</code>'
            '</div>'
            '<div class="news-batch-stats">'
            f'<span><b>{_esc(batch.get("count"))}</b> noticias</span>'
            f'<span>{_esc(" · ".join(str(value) for value in batch.get("categories", [])))}</span>'
            '</div>'
            '</div>'
            f'<div class="news-grid">{"".join(news_cards)}</div>'
            '</section>'
        )
    news_html = "".join(news_sections) or '<p class="empty">No hay depósitos parseables en news/.</p>'

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
:root{{--bg:#080d13;--panel:#0e1620;--panel2:#111d29;--line:#223247;--text:#edf6ff;--muted:#8799aa;--accent:#6edaff;--story:#c7a6ff;--story-bg:#181327;--news:#6edaff;--news-bg:#0d1c27;--ok:#5bd0a3;--warn:#f2be62;--cool:#aa8cff}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:radial-gradient(circle at 20% 0,#102638 0,transparent 34%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
button,input{{font:inherit}}button{{cursor:pointer}}main{{max-width:1500px;margin:auto;padding:34px 30px 70px}}.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:850}}
.hero{{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,.8fr);gap:28px;align-items:end;margin-bottom:18px}}h1{{font-size:clamp(34px,5vw,66px);line-height:.96;margin:8px 0 14px;letter-spacing:-.045em}}.hero p{{max-width:850px;color:#a9bac9;font-size:15px;line-height:1.65;margin:0}}.freshness{{background:#0d1924;border:1px solid var(--line);border-radius:16px;padding:17px}}.freshness strong{{display:block;font-size:20px;margin-top:4px}}.freshness small{{color:var(--muted)}}
.source-legend{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0 22px}}.source-card{{border:1px solid var(--line);border-radius:15px;padding:14px 16px;display:flex;gap:12px;align-items:flex-start}}.source-card.story{{background:linear-gradient(135deg,var(--story-bg),#101720);border-color:#4e3d6e}}.source-card.news{{background:linear-gradient(135deg,var(--news-bg),#101720);border-color:#28546b}}.source-dot{{width:10px;height:10px;border-radius:50%;margin-top:4px;flex:0 0 auto}}.story .source-dot{{background:var(--story)}}.news .source-dot{{background:var(--news)}}.source-card strong{{display:block;font-size:13px}}.source-card small{{display:block;color:var(--muted);margin-top:3px;line-height:1.4}}
.kpis{{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:10px;margin:18px 0}}.kpi{{background:linear-gradient(180deg,#111c28,#0c141d);border:1px solid var(--line);border-radius:15px;padding:15px}}.kpi span{{display:block;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em}}.kpi b{{display:block;font-size:28px;margin-top:5px;letter-spacing:-.03em}}.kpi small{{color:#8ea2b5;font-size:10px}}
.tabs{{display:flex;gap:7px;flex-wrap:wrap;margin:22px 0 8px;padding:5px;background:#0b131c;border:1px solid var(--line);border-radius:14px;width:max-content;max-width:100%}}.tab-button{{appearance:none;border:0;background:transparent;color:#8fa3b5;border-radius:10px;padding:10px 13px;font-size:11px;font-weight:850}}.tab-button.active{{background:#152433;color:var(--text);box-shadow:inset 0 0 0 1px #294057}}.tab-panel[hidden]{{display:none}}
.section-intro{{margin:12px 0 14px;border-radius:15px;padding:15px 17px;border:1px solid var(--line)}}.section-intro.story{{background:linear-gradient(135deg,#181327,#0e1720);border-color:#493967}}.section-intro.news{{background:linear-gradient(135deg,#0d1c27,#0e1720);border-color:#28546b}}.section-intro h2{{margin:3px 0 4px;font-size:20px}}.section-intro p{{margin:0;color:#9eb0bf;font-size:12px;line-height:1.5}}
.controls{{position:sticky;top:0;z-index:5;padding:10px 0 12px;background:linear-gradient(180deg,#080d13 78%,transparent)}}.search-row{{display:grid;grid-template-columns:minmax(260px,1fr) auto;gap:8px;margin-bottom:8px}}input[type="search"]{{width:100%;background:#0c151f;color:var(--text);border:1px solid var(--line);border-radius:11px;padding:11px 12px;outline:none}}input[type="search"]:focus{{border-color:#4c9ec0;box-shadow:0 0 0 3px #17405a55}}.reset-button{{border:1px solid var(--line);background:#101923;color:#9fb0bf;border-radius:11px;padding:0 13px;font-size:10px;font-weight:800}}
.control-line{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:6px 0}}.control-label{{color:#708699;font-size:9px;text-transform:uppercase;letter-spacing:.1em;font-weight:850;margin-right:2px}}.results-count{{margin-left:auto;color:#8297a8;font-size:10px;font-variant-numeric:tabular-nums}}.filter-chip,.sort-chip{{border:1px solid #2b3d4e;background:#0d1720;color:#99adbd;border-radius:999px;padding:6px 9px;font-size:10px;line-height:1}}.filter-chip span{{opacity:.65}}.filter-chip:hover,.sort-chip:hover{{border-color:#4b6d86;color:#dceaf4}}.filter-chip.active{{background:#173146;border-color:#4380a4;color:#d9f4ff}}.story-filters .filter-chip.active{{background:#2b2140;border-color:#725b9d;color:#e6d9ff}}.sort-chip.active{{background:#132b38;border-color:#3b7898;color:#cdefff}}.sort-chip .arrow{{display:inline-block;min-width:10px;margin-left:3px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}}.memory-card{{background:linear-gradient(180deg,#151522,#0d151e);border:1px solid #382f4d;border-radius:17px;padding:18px;min-width:0}}.memory-card[hidden]{{display:none}}.card-top{{display:flex;justify-content:space-between;align-items:center;gap:12px}}.card-freshness{{display:flex;align-items:center;gap:8px;color:#7f93a5;font-size:10px}}.availability{{font-size:9px;font-weight:900;letter-spacing:.1em;border-radius:999px;padding:5px 8px;border:1px solid}}.availability.available{{color:var(--ok);border-color:#28644f;background:#10271f}}.availability.cooldown{{color:var(--cool);border-color:#574985;background:#1c1830}}.quality{{font-size:11px;color:#d8c6ff;font-variant-numeric:tabular-nums}}.memory-card h3{{font-size:19px;margin:11px 0 6px}}.one-liner{{margin:0;color:#a9bac9;line-height:1.5;font-size:13px}}.chips{{display:flex;gap:5px;flex-wrap:wrap;margin:12px 0}}.chip{{font-size:9px;border:1px solid #304153;background:#111b25;color:#aabaca;border-radius:999px;padding:4px 7px}}.chip.mechanism{{border-color:#5a477b;color:#d0baff;background:#1b1728}}.score-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:13px 0}}.score-grid span{{display:grid;gap:1px;background:#09121a;border:1px solid #1d2c3d;border-radius:10px;padding:9px;color:var(--muted);font-size:9px}}.score-grid b{{font-size:17px;color:var(--text)}}.card-meta{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;color:#8497a9;font-size:10px;margin-bottom:8px}}details{{border-top:1px solid #1d2c3b;padding-top:10px}}summary{{cursor:pointer;color:#9adcf4;font-size:11px;font-weight:750}}details p{{color:#9dafbd;line-height:1.55;font-size:11px}}.sources{{display:flex;gap:7px;flex-wrap:wrap}}.sources a{{color:var(--accent);font-size:10px}}
.news-batch{{margin:18px 0 30px}}.news-batch[hidden]{{display:none}}.news-batch-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:11px;padding-bottom:10px;border-bottom:1px solid #1d3342}}.news-batch-head h2{{font-size:23px;margin:3px 0 2px}}.news-batch-head code{{font-size:9px;color:#6f8ea2}}.news-batch-stats{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:#7892a5;font-size:9px}}.news-batch-stats span{{border:1px solid #233b4b;background:#0d1a23;border-radius:999px;padding:6px 9px}}.news-batch-stats b{{color:#bdeeff}}.news-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}.news-card{{background:linear-gradient(180deg,#101d27,#0c151d);border:1px solid #244052;border-radius:15px;padding:15px;min-width:0}}.news-card[hidden]{{display:none}}.news-card-top{{display:flex;justify-content:space-between;gap:10px;align-items:center}}.news-category{{font-size:9px;color:#bdeeff;text-transform:uppercase;letter-spacing:.08em}}.news-source{{font-size:9px;color:#718b9c;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:55%}}.news-card h3{{font-size:15px;line-height:1.3;margin:9px 0 6px}}.news-card>p{{font-size:11px;line-height:1.5;color:#9dafbd;margin:0 0 10px}}.news-card details{{margin-top:7px}}.news-link{{display:inline-block;margin-top:10px;color:var(--news);font-size:10px;text-decoration:none}}.muted-link{{color:#617584}}
.section-grid{{display:grid;grid-template-columns:minmax(320px,.8fr) minmax(0,1.2fr);gap:14px;margin:28px 0}}.panel{{background:#0d151e;border:1px solid var(--line);border-radius:17px;padding:18px}}.panel h2{{font-size:19px;margin:4px 0 15px}}.mechanism-row{{display:grid;grid-template-columns:minmax(190px,1fr) minmax(100px,.65fr);gap:12px;align-items:center;margin:8px 0}}.mechanism-row>div:first-child{{display:flex;justify-content:space-between;gap:9px;font-size:10px}}.mechanism-row span{{color:var(--muted)}}.bar{{height:7px;background:#091018;border-radius:99px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,#805fb3,#c7a6ff);border-radius:99px}}table{{width:100%;border-collapse:collapse;font-size:11px}}th,td{{text-align:left;padding:9px 7px;border-bottom:1px solid #1c2a39;vertical-align:top}}th{{color:#8ca0b3;font-size:9px;text-transform:uppercase;letter-spacing:.08em}}.empty{{color:var(--muted);font-size:12px}}.warning,.ok-note{{margin-top:18px;border-radius:13px;padding:13px;font-size:11px;line-height:1.5}}.warning{{border:1px solid #6c5325;background:#261d0d;color:#e9c87e}}.ok-note{{border:1px solid #255744;background:#10251d;color:#84d9b8}}.footer-note{{margin-top:24px;color:#718597;font-size:10px}}
@media(max-width:1180px){{.news-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:1000px){{.hero{{grid-template-columns:1fr}}.kpis{{grid-template-columns:repeat(3,1fr)}}.grid,.section-grid{{grid-template-columns:1fr}}.source-legend{{grid-template-columns:1fr}}}}@media(max-width:680px){{main{{padding:22px 14px 50px}}.kpis{{grid-template-columns:repeat(2,1fr)}}.controls{{position:static}}.search-row{{grid-template-columns:1fr}}.score-grid{{grid-template-columns:repeat(2,1fr)}}.news-grid{{grid-template-columns:1fr}}.news-batch-head{{align-items:flex-start;flex-direction:column}}}}
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
<div class="source-legend">
<div class="source-card story"><span class="source-dot"></span><div><strong>Historias interesantes</strong><small>Casos verificados y reutilizables de Narrative Memory. Tienen sorpresa, analogía, calidad y cooldown.</small></div></div>
<div class="source-card news"><span class="source-dot"></span><div><strong>Noticias diarias</strong><small>Entradas que realmente se depositan en <code>news/</code>. Son el input factual diario; no son Narrative Memory.</small></div></div>
</div>
<nav class="tabs" aria-label="Secciones de Editorial Memory">
<button class="tab-button active" type="button" data-memory-tab="stories">Historias interesantes · {_esc(metrics.get("approved_items"))}</button>
<button class="tab-button" type="button" data-memory-tab="news">Noticias diarias · {_esc(news.get("batch_count", 0))} depósitos</button>
<button class="tab-button" type="button" data-memory-tab="coverage">Cobertura &amp; uso</button>
</nav>
<section class="tab-panel" data-memory-panel="stories">
<div class="section-intro story"><span class="eyebrow">Narrative Memory</span><h2>Historias interesantes</h2><p>Contexto histórico, científico o económico para enriquecer el ensayo. Por defecto: lo más reciente y sorprendente primero.</p></div>
<div class="controls story-filters">
<div class="search-row"><input id="memorySearch" type="search" placeholder="Buscar historia, dominio o mecanismo…" aria-label="Buscar historias interesantes"><button id="storyReset" type="button" class="reset-button">Limpiar</button></div>
<div class="control-line"><span class="control-label">Ordenar</span>
<button type="button" class="sort-chip active" data-story-sort="date" data-direction="desc">Recientes <span class="arrow">↓</span></button>
<button type="button" class="sort-chip" data-story-sort="surprise" data-direction="desc">Sorpresa <span class="arrow">↓</span></button>
<button type="button" class="sort-chip" data-story-sort="quality" data-direction="desc">Calidad <span class="arrow">↓</span></button>
<span id="storyResultCount" class="results-count" aria-live="polite"></span>
</div>
<div class="control-line"><span class="control-label">Mostrar</span>
<button type="button" class="filter-chip active" data-story-availability="" aria-pressed="true">Todas</button>
<button type="button" class="filter-chip" data-story-availability="available" aria-pressed="false">Disponibles</button>
<button type="button" class="filter-chip" data-story-availability="cooldown" aria-pressed="false">Cooldown</button>
</div>
</div>
<section id="memoryGrid" class="grid">{"".join(cards)}</section>
<div id="emptyMemory" class="empty" hidden>No hay historias que coincidan con esos filtros.</div>
</section>
<section class="tab-panel" data-memory-panel="news" hidden>
<div class="section-intro news"><span class="eyebrow">news/*.txt</span><h2>Noticias diarias</h2><p>{_esc(news.get("item_count", 0))} noticias en {_esc(news.get("batch_count", 0))} depósitos parseables. Último archivo: <code>{_esc(news.get("latest_source_file"))}</code>.</p></div>
<div class="controls">
<div class="search-row"><input id="newsSearch" type="search" placeholder="Buscar noticia, fuente o categoría…" aria-label="Buscar noticias diarias"><button id="newsReset" type="button" class="reset-button">Limpiar</button></div>
<div class="control-line"><span class="control-label">Ordenar depósitos</span><button type="button" id="newsDateSort" class="sort-chip active" data-direction="desc">Fecha <span class="arrow">↓</span></button><span class="control-label">Categoría</span>{news_category_buttons}</div>
</div>
<div id="newsFeed">{news_html}</div>
<div id="emptyNews" class="empty" hidden>No hay noticias que coincidan con ese filtro.</div>
</section>
<section class="tab-panel" data-memory-panel="coverage" hidden>
<section class="section-grid">
<div class="panel"><span class="eyebrow">Narrative Memory</span><h2>Mecanismos narrativos</h2>{mechanism_cards or '<p class="empty">Sin mecanismos disponibles.</p>'}<p class="footer-note">Concentración del mecanismo más frecuente: {_esc(metrics.get("primary_mechanism_concentration"))}.</p></div>
<div class="panel"><span class="eyebrow">Uso real</span><h2>Qué historias llegaron a episodios aprobados</h2><table><thead><tr><th>Episodio</th><th>Historias</th><th>Total</th></tr></thead><tbody>{episode_rows if episode_rows else '<tr><td colspan="3" class="empty">Aún no hay usos aprobados registrados.</td></tr>'}</tbody></table></div>
</section>
{issues_block}
</section>
<p class="footer-note">Noticias diarias y Narrative Memory son fuentes distintas: <code>news/</code> aporta hechos recientes; <code>editorial/narrative_memory.jsonl</code> aporta paralelos verificados y reutilizables. Esta vista no mezcla sus métricas ni sus filtros.</p>
</main>
<script>
const norm=value=>(value||'').toLocaleLowerCase('es');
const storyCards=[...document.querySelectorAll('[data-memory-card]')];
const storyGrid=document.getElementById('memoryGrid');
const storySearch=document.getElementById('memorySearch');
const storyEmpty=document.getElementById('emptyMemory');
const storyResultCount=document.getElementById('storyResultCount');
const storyState={{availability:'',sort:'date',direction:'desc'}};
function setStoryAvailability(value,button){{
  storyState.availability=value||'';
  document.querySelectorAll('[data-story-availability]').forEach(item=>{{
    const active=item===button;
    item.classList.toggle('active',active);
    item.setAttribute('aria-pressed',active?'true':'false');
  }});
  applyStoryView();
}}
function compareStory(a,b){{
  const dir=storyState.direction==='asc'?1:-1;
  let left,right;
  if(storyState.sort==='surprise'){{left=Number(a.dataset.surprise)||0;right=Number(b.dataset.surprise)||0;}}
  else if(storyState.sort==='quality'){{left=Number(a.dataset.quality)||0;right=Number(b.dataset.quality)||0;}}
  else{{left=a.dataset.createdAt||'';right=b.dataset.createdAt||'';}}
  if(left<right)return -1*dir;if(left>right)return 1*dir;
  return (Number(b.dataset.surprise)||0)-(Number(a.dataset.surprise)||0);
}}
function applyStoryView(){{
  const q=norm(storySearch?.value).trim();let visible=0;
  storyCards.forEach(card=>{{
    const hit=(!q||norm(card.dataset.search).includes(q))
      &&(!storyState.availability||card.dataset.availability===storyState.availability);
    card.hidden=!hit;if(hit)visible+=1;
  }});
  [...storyCards].sort(compareStory).forEach(card=>storyGrid.appendChild(card));
  storyEmpty.hidden=visible!==0;
  if(storyResultCount)storyResultCount.textContent='Mostrando '+visible+' de '+storyCards.length+' historias';
}}
document.querySelectorAll('[data-story-availability]').forEach(button=>button.addEventListener('click',()=>setStoryAvailability(button.dataset.storyAvailability||'',button)));
document.querySelectorAll('[data-story-sort]').forEach(button=>button.addEventListener('click',()=>{{
  const key=button.dataset.storySort;
  if(storyState.sort===key)storyState.direction=storyState.direction==='desc'?'asc':'desc';
  else{{storyState.sort=key;storyState.direction='desc';}}
  document.querySelectorAll('[data-story-sort]').forEach(item=>{{
    const active=item.dataset.storySort===storyState.sort;item.classList.toggle('active',active);
    item.querySelector('.arrow').textContent=active?(storyState.direction==='desc'?'↓':'↑'):'↓';
  }});
  applyStoryView();
}}));
storySearch?.addEventListener('input',applyStoryView);
document.getElementById('storyReset')?.addEventListener('click',()=>{{
  storyState.availability='';storyState.sort='date';storyState.direction='desc';
  if(storySearch)storySearch.value='';
  document.querySelectorAll('[data-story-availability]').forEach(item=>{{
    const active=(item.dataset.storyAvailability||'')==='';
    item.classList.toggle('active',active);
    item.setAttribute('aria-pressed',active?'true':'false');
  }});
  document.querySelectorAll('[data-story-sort]').forEach(item=>{{const active=item.dataset.storySort==='date';item.classList.toggle('active',active);item.querySelector('.arrow').textContent='↓';}});
  applyStoryView();
}}));

const newsBatches=[...document.querySelectorAll('[data-news-batch]')];
const newsCards=[...document.querySelectorAll('[data-news-card]')];
const newsFeed=document.getElementById('newsFeed');
const newsSearch=document.getElementById('newsSearch');
const newsEmpty=document.getElementById('emptyNews');
let newsCategory='';let newsDirection='desc';
function applyNewsView(){{
  const q=norm(newsSearch?.value).trim();let totalVisible=0;
  newsBatches.forEach(batch=>{{
    let batchVisible=0;
    batch.querySelectorAll('[data-news-card]').forEach(card=>{{
      const hit=(!q||norm(card.dataset.search).includes(q))&&(!newsCategory||norm(card.dataset.category)===norm(newsCategory));
      card.hidden=!hit;if(hit){{batchVisible+=1;totalVisible+=1;}}
    }});
    batch.hidden=batchVisible===0;
  }});
  [...newsBatches].sort((a,b)=>newsDirection==='desc'
    ?(b.dataset.depositKey||'').localeCompare(a.dataset.depositKey||'')
    :(a.dataset.depositKey||'').localeCompare(b.dataset.depositKey||'')
  ).forEach(batch=>newsFeed.appendChild(batch));
  newsEmpty.hidden=totalVisible!==0;
}}
document.querySelectorAll('[data-news-category]').forEach(button=>button.addEventListener('click',()=>{{
  const value=button.dataset.newsCategory||'';newsCategory=newsCategory===value?'':value;
  document.querySelectorAll('[data-news-category]').forEach(item=>item.classList.toggle('active',item===button&&Boolean(newsCategory)));
  applyNewsView();
}}));
document.getElementById('newsDateSort')?.addEventListener('click',event=>{{
  newsDirection=newsDirection==='desc'?'asc':'desc';event.currentTarget.dataset.direction=newsDirection;
  event.currentTarget.querySelector('.arrow').textContent=newsDirection==='desc'?'↓':'↑';applyNewsView();
}});
newsSearch?.addEventListener('input',applyNewsView);
document.getElementById('newsReset')?.addEventListener('click',()=>{{
  newsCategory='';newsDirection='desc';if(newsSearch)newsSearch.value='';
  document.querySelectorAll('[data-news-category]').forEach(item=>item.classList.remove('active'));
  const sort=document.getElementById('newsDateSort');if(sort)sort.querySelector('.arrow').textContent='↓';
  applyNewsView();
}}));

document.querySelectorAll('[data-memory-tab]').forEach(button=>button.addEventListener('click',()=>{{
  const target=button.dataset.memoryTab;
  document.querySelectorAll('[data-memory-tab]').forEach(item=>item.classList.toggle('active',item===button));
  document.querySelectorAll('[data-memory-panel]').forEach(panel=>panel.hidden=panel.dataset.memoryPanel!==target);
}}));
applyStoryView();applyNewsView();
</script>
</body>
</html>
"""


def build_dashboard(
    *,
    memory_path: Path,
    scripts_root: Path,
    output_dir: Path,
    news_root: Path | None = None,
    as_of: date | None = None,
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS,
) -> Path:
    report = build_report(
        memory_path=memory_path,
        scripts_root=scripts_root,
        news_root=news_root,
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
    parser.add_argument("--news-root", default="news")
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
        news_root=Path(args.news_root),
        output_dir=Path(args.output_dir),
        as_of=as_of,
        cooldown_days=args.cooldown_days,
    )
    print(result)


if __name__ == "__main__":
    main()
