from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

from pipeline.costs import build_cost_snapshot
from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v6 import build_site as _build_site_v6


def _usd(value: Any, *, precise: bool = False) -> str:
    try:
        if value is None or value == "":
            return "—"
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if precise or abs(number) < 0.01:
        return f"${number:,.4f}"
    return f"${number:,.2f}"


def _integer(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "—"


def _seconds(value: Any) -> str:
    try:
        return f"{float(value or 0):,.1f}s"
    except (TypeError, ValueError):
        return "—"


def _bytes(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while amount >= 1024 and index < len(units) - 1:
        amount /= 1024
        index += 1
    decimals = 0 if index == 0 else 1 if amount >= 10 else 2
    return f"{amount:,.{decimals}f} {units[index]}"


def _pct(value: Any) -> str:
    try:
        if value is None:
            return "—"
        return f"{float(value):,.1f}%"
    except (TypeError, ValueError):
        return "—"


def _status_text(snapshot: dict[str, Any]) -> tuple[str, str]:
    budget = snapshot.get("budget", {}) if isinstance(snapshot, dict) else {}
    status = str(budget.get("status") or "not_configured")
    if status == "over_budget":
        return "Sobre presupuesto", "bad"
    if status == "within_budget":
        return "Dentro de presupuesto", "ok"
    return "Presupuesto no configurado", "neutral"


def _pricing_note(snapshot: dict[str, Any]) -> str:
    pricing = snapshot.get("pricing_snapshot", {}) if isinstance(snapshot, dict) else {}
    model = html.escape(str(pricing.get("production_model") or "—"))
    rate = pricing.get("production_rate", {}) if isinstance(pricing.get("production_rate"), dict) else {}
    input_rate = rate.get("input_per_million")
    output_rate = rate.get("output_per_million")
    as_of = html.escape(str(pricing.get("as_of") or "—"))
    if input_rate is None or output_rate is None:
        return f"Tarifa no versionada para {model}. Snapshot: {as_of}."
    return (
        f"{model} · {_usd(input_rate, precise=True)}/1M input · "
        f"{_usd(output_rate, precise=True)}/1M output · snapshot {as_of}."
    )


def _summary_cards(snapshot: dict[str, Any]) -> str:
    budget = snapshot.get("budget", {}) if isinstance(snapshot, dict) else {}
    totals = snapshot.get("totals", {}) if isinstance(snapshot, dict) else {}
    usage = snapshot.get("usage", {}) if isinstance(snapshot, dict) else {}
    configured = budget.get("configured_usd")
    remaining = budget.get("remaining_usd")
    utilization = budget.get("utilization_pct")
    cards = [
        ("Costo directo conocido", _usd(totals.get("known_direct_cost_usd")), "OpenAI + servicios con costo determinable"),
        ("Presupuesto episodio", _usd(configured), "Configurable con REVIEW_HUB_EPISODE_BUDGET_USD" if configured is None else f"Uso: {_pct(utilization)}"),
        ("Disponible", _usd(remaining), "No calculable hasta configurar presupuesto" if remaining is None else "Presupuesto − costo directo conocido"),
        ("Tokens observados", _integer(usage.get("total_tokens")), f"{_integer(usage.get('prompt_tokens'))} input · {_integer(usage.get('output_tokens'))} output"),
    ]
    return '<div class="budget-kpis">' + "".join(
        '<div class="budget-kpi" data-search-item>'
        f'<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><small>{html.escape(note)}</small>'
        '</div>'
        for label, value, note in cards
    ) + '</div>'


def _service_cards(snapshot: dict[str, Any]) -> str:
    totals = snapshot.get("totals", {}) if isinstance(snapshot, dict) else {}
    usage = snapshot.get("usage", {}) if isinstance(snapshot, dict) else {}
    multimedia = snapshot.get("multimedia", {}) if isinstance(snapshot, dict) else {}
    github = snapshot.get("github", {}) if isinstance(snapshot, dict) else {}
    provider_counts = multimedia.get("provider_counts", {}) if isinstance(multimedia.get("provider_counts"), dict) else {}
    pexels_assets = int(multimedia.get("pexels_assets", 0) or 0)
    cards = [
        (
            "OpenAI API",
            _usd(totals.get("known_openai_cost_usd")),
            f"{_integer(usage.get('attempts_with_observed_usage'))} intentos con uso · {_integer(usage.get('prompt_tokens'))} input · {_integer(usage.get('output_tokens'))} output",
            "calculated",
        ),
        (
            "Pexels API",
            _usd(totals.get("pexels_known_cost_usd")),
            f"{pexels_assets} assets Pexels · requests exactos no persistidos" if pexels_assets else f"Providers: {provider_counts or '—'}",
            "policy",
        ),
        (
            "GitHub Actions compute",
            _usd(totals.get("github_actions_compute_known_cost_usd")),
            "Repo público + runner estándar: sin cargo de compute según política vigente",
            "policy",
        ),
        (
            "Artifact storage",
            _usd(totals.get("artifact_storage_gross_exposure_usd")),
            f"Exposición bruta si todo fuera billable · {_bytes(github.get('raw_artifact_upload_bytes_estimate'))} raw · 30 días · excluido del total",
            "exposure",
        ),
    ]
    return '<div class="service-grid">' + "".join(
        '<article class="service-card" data-search-item>'
        f'<div class="service-top"><h3>{html.escape(label)}</h3><span class="cost-kind {kind}">{html.escape(kind)}</span></div>'
        f'<strong>{html.escape(value)}</strong><p>{html.escape(note)}</p></article>'
        for label, value, note, kind in cards
    ) + '</div>'


def _step_table(snapshot: dict[str, Any]) -> str:
    rows = snapshot.get("breakdown_by_step", []) if isinstance(snapshot, dict) else []
    body: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        blob = " ".join(str(row.get(key) or "") for key in ("scope", "step", "agent"))
        body.append(
            f'<tr data-search-item data-search-text="{html.escape(blob, quote=True)}">'
            f'<td><span class="scope-pill">{html.escape(str(row.get("scope") or "—"))}</span></td>'
            f'<td><strong>{html.escape(str(row.get("step") or "—"))}</strong><small>{html.escape(str(row.get("agent") or "—"))}</small></td>'
            f'<td>{_integer(row.get("attempts"))}</td>'
            f'<td>{_integer(row.get("errors"))}</td>'
            f'<td>{_integer(row.get("prompt_tokens"))}</td>'
            f'<td>{_integer(row.get("billable_output_tokens"))}</td>'
            f'<td>{_seconds(row.get("elapsed_seconds"))}</td>'
            f'<td class="money">{_usd(row.get("estimated_cost_usd"), precise=True)}</td>'
            '</tr>'
        )
    if not body:
        body.append('<tr><td colspan="8" class="muted">No hay uso de modelo persistido para desglosar.</td></tr>')
    return (
        '<div class="budget-table-wrap"><table class="budget-table"><thead><tr>'
        '<th>Scope</th><th>Paso / agente</th><th>Intentos</th><th>Errores</th><th>Input</th><th>Output billable</th><th>Tiempo</th><th>Costo</th>'
        '</tr></thead><tbody>' + "".join(body) + '</tbody></table></div>'
    )


def _attempt_table(snapshot: dict[str, Any]) -> str:
    rows = snapshot.get("attempts", []) if isinstance(snapshot, dict) else []
    body: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        cost = row.get("estimated_cost_usd")
        cost_text = _usd(cost, precise=True) if cost is not None else "—"
        iteration = row.get("iteration")
        sequence = f"#{_integer(row.get('sequence'))}"
        if iteration is not None:
            sequence += f" · iter {iteration}"
        body.append(
            '<tr data-search-item>'
            f'<td>{html.escape(str(row.get("scope") or "—"))}</td>'
            f'<td>{html.escape(str(row.get("step") or "—"))}<small>{html.escape(str(row.get("agent") or "—"))}</small></td>'
            f'<td>{html.escape(sequence)}</td>'
            f'<td>{_integer(row.get("attempt"))}</td>'
            f'<td><span class="attempt-status {html.escape(str(row.get("status") or "unknown"))}">{html.escape(str(row.get("status") or "unknown"))}</span></td>'
            f'<td>{_integer(row.get("prompt_tokens"))}</td>'
            f'<td>{_integer(row.get("output_tokens"))}</td>'
            f'<td>{_integer(row.get("reasoning_tokens"))}</td>'
            f'<td>{_integer(row.get("total_tokens"))}</td>'
            f'<td>{_seconds(row.get("elapsed_seconds"))}</td>'
            f'<td class="money">{html.escape(cost_text)}</td>'
            '</tr>'
        )
    return (
        '<details class="cost-details"><summary>Ver cada intento del modelo</summary>'
        '<div class="budget-table-wrap"><table class="budget-table attempts"><thead><tr>'
        '<th>Scope</th><th>Paso / agente</th><th>Secuencia</th><th>Attempt</th><th>Status</th><th>Input</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Tiempo</th><th>Costo</th>'
        '</tr></thead><tbody>' + ("".join(body) if body else '<tr><td colspan="11">Sin intentos persistidos.</td></tr>') + '</tbody></table></div></details>'
    )


def _coverage(snapshot: dict[str, Any]) -> str:
    coverage = snapshot.get("coverage", {}) if isinstance(snapshot, dict) else {}
    warnings = coverage.get("warnings", []) if isinstance(coverage, dict) else []
    completeness = bool(coverage.get("known_direct_total_is_complete"))
    items = [
        ("Costo directo", "Completo para uso persistido" if completeness else "Es un piso: hay uso sin medir o sin precio", completeness),
        ("Cached input", "No medido; se cobra conservadoramente como input estándar", False),
        ("Pexels requests", "No se persiste el conteo exacto de requests; costo monetario de API = 0 según snapshot", False),
        ("GitHub billing", "La página no tiene acceso a la utilización de facturación de la cuenta; storage se muestra como exposición bruta", False),
    ]
    checks = '<div class="coverage-grid">' + "".join(
        '<div class="coverage-item" data-search-item>'
        f'<span class="coverage-dot {"ok" if ok else "warn"}"></span><div><strong>{html.escape(label)}</strong><p>{html.escape(text)}</p></div></div>'
        for label, text, ok in items
    ) + '</div>'
    warning_html = ""
    if isinstance(warnings, list) and warnings:
        warning_html = '<details class="cost-details"><summary>Advertencias de medición</summary><ul class="cost-warnings">' + "".join(
            f'<li data-search-item>{html.escape(str(item))}</li>' for item in warnings
        ) + '</ul></details>'
    return checks + warning_html


def _source_links(snapshot: dict[str, Any]) -> str:
    sources = snapshot.get("sources", {}) if isinstance(snapshot, dict) else {}
    labels = (
        ("OpenAI pricing", sources.get("openai")),
        ("Pexels API", sources.get("pexels")),
        ("GitHub Actions", sources.get("github_actions")),
        ("GitHub artifact storage", sources.get("github_storage")),
    )
    links = []
    for label, url in labels:
        if not url:
            continue
        links.append(f'<a href="{html.escape(str(url), quote=True)}" target="_blank" rel="noreferrer">{html.escape(label)}</a>')
    return '<div class="cost-sources"><span>Fuentes de tarifa:</span>' + " · ".join(links) + '</div>'


def budget_panel(snapshot: dict[str, Any]) -> str:
    status_text, status_class = _status_text(snapshot)
    budget = snapshot.get("budget", {}) if isinstance(snapshot, dict) else {}
    remaining = budget.get("remaining_usd")
    return (
        '<section id="budget" class="budget-section" data-search-group aria-labelledby="budget-title">'
        '<div class="budget-heading"><div><span class="eyebrow">FinOps del episodio</span>'
        '<h2 id="budget-title">Budget & Costs</h2><p>Presupuesto, consumo observado y costo estimado con trazabilidad hasta cada llamada.</p></div>'
        f'<div class="budget-state"><span class="badge {status_class}">{html.escape(status_text)}</span>'
        f'<strong>{_usd(remaining) if remaining is not None else _usd(budget.get("known_direct_cost_usd"))}</strong>'
        f'<small>{"disponible" if remaining is not None else "costo directo conocido"}</small></div></div>'
        + _summary_cards(snapshot)
        + f'<p class="pricing-note">{html.escape(_pricing_note(snapshot))} Los cached tokens no están separados en el trace, por lo que el input se estima conservadoramente a tarifa estándar.</p>'
        + '<div class="budget-section-heading"><h3>Servicios</h3><p>Qué tiene costo, qué es gratis por política y qué depende de la facturación de la cuenta.</p></div>'
        + _service_cards(snapshot)
        + '<div class="budget-section-heading"><h3>Costo por paso</h3><p>Agregado por agente/step; los montos usan únicamente tokens realmente persistidos.</p></div>'
        + _step_table(snapshot)
        + _attempt_table(snapshot)
        + '<div class="budget-section-heading"><h3>Cobertura de medición</h3><p>Lo que sabemos con certeza y lo que todavía no puede reconstruirse.</p></div>'
        + _coverage(snapshot)
        + '<div class="cost-download"><a class="button" href="downloads/cost_snapshot.json" download>Descargar cost_snapshot.json</a></div>'
        + _source_links(snapshot)
        + '</section>'
    )


BUDGET_CSS = r"""
/* v7: dedicated FinOps / budget workspace. */
.budget-section{padding:22px 0 10px}.budget-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:24px;margin-bottom:18px}.budget-heading h2{margin:4px 0 6px}.budget-heading p{margin:0;color:var(--muted);max-width:720px}.budget-state{display:grid;justify-items:end;gap:3px;min-width:180px}.budget-state>strong{font-size:30px;line-height:1.05}.budget-state>small{color:var(--muted)}
.budget-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.budget-kpi{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:15px}.budget-kpi>span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.07em}.budget-kpi>strong{display:block;font-size:25px;margin:7px 0 5px}.budget-kpi>small{display:block;color:#aebdcd;line-height:1.35}.pricing-note{margin:11px 0 22px;padding:11px 13px;border-left:3px solid #315b78;background:#101a25;color:#aebdcd;font-size:12px;line-height:1.55}.budget-section-heading{display:flex;justify-content:space-between;gap:18px;align-items:end;margin:25px 0 10px}.budget-section-heading h3{margin:0}.budget-section-heading p{margin:0;color:var(--muted);font-size:12px;text-align:right}
.service-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.service-card{border:1px solid var(--line);border-radius:15px;background:var(--panel);padding:15px}.service-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.service-card h3{font-size:14px;margin:0}.service-card>strong{display:block;font-size:24px;margin:10px 0 6px}.service-card p{margin:0;color:var(--muted);font-size:12px;line-height:1.45}.cost-kind{font-size:9px;text-transform:uppercase;letter-spacing:.07em;padding:3px 6px;border-radius:999px;background:#1b2938;color:#adbed0}.cost-kind.calculated{color:#bfe9ff;background:#163047}.cost-kind.policy{color:#bce8d8;background:#153127}.cost-kind.exposure{color:#f0d3a5;background:#3a2b17}
.budget-table-wrap{overflow:auto;border:1px solid var(--line);border-radius:14px;background:#101722}.budget-table{width:100%;border-collapse:collapse;min-width:860px;font-size:12px}.budget-table th{position:sticky;top:0;background:#161f2c;color:#91a5ba;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.06em;padding:10px 11px;border-bottom:1px solid var(--line)}.budget-table td{padding:10px 11px;border-top:1px solid #243143;vertical-align:top}.budget-table tbody tr:first-child td{border-top:0}.budget-table td small{display:block;color:var(--muted);margin-top:3px}.budget-table .money{text-align:right;font-variant-numeric:tabular-nums;font-weight:800}.scope-pill{display:inline-block;padding:3px 6px;border-radius:7px;background:#19283a;color:#b6cadc;font-size:10px}.attempt-status{display:inline-block;padding:2px 6px;border-radius:999px;background:#242f3d}.attempt-status.success{color:#bce8d8;background:#153127}.attempt-status.error{color:#ffc0c9;background:#3b1c27}
.cost-details{margin-top:10px;border:1px solid var(--line);border-radius:13px;background:#0f151f}.cost-details>summary{cursor:pointer;padding:11px 13px;font-weight:760;color:#bdd0e2}.cost-details>.budget-table-wrap{border:0;border-top:1px solid var(--line);border-radius:0}.coverage-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.coverage-item{display:flex;gap:10px;border:1px solid var(--line);border-radius:13px;padding:12px;background:var(--panel)}.coverage-item strong{font-size:12px}.coverage-item p{margin:3px 0 0;color:var(--muted);font-size:12px;line-height:1.4}.coverage-dot{width:9px;height:9px;border-radius:50%;margin-top:4px;flex:0 0 auto;background:#bd8740}.coverage-dot.ok{background:#53b88f}.cost-warnings{margin:0;padding:0 30px 13px;color:#d9c3a4}.cost-warnings li{margin:7px 0}.cost-download{margin:17px 0 10px}.cost-sources{color:var(--muted);font-size:11px;margin-top:12px}.cost-sources span{margin-right:5px}.cost-sources a{color:#9bdcff}
@media(max-width:900px){.budget-kpis,.service-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:620px){.budget-heading{flex-direction:column}.budget-state{justify-items:start}.budget-kpis,.service-grid,.coverage-grid{grid-template-columns:1fr}.budget-section-heading{display:block}.budget-section-heading p{text-align:left;margin-top:4px}.budget-kpi>strong,.service-card>strong{font-size:22px}}
"""


def apply_budget_workspace(document: str, snapshot: dict[str, Any]) -> str:
    document = document.replace("</style>", BUDGET_CSS + "\n</style>", 1)
    technical_tab = '<button id="tab-technical"'
    tab_at = document.find(technical_tab)
    if tab_at < 0:
        raise RuntimeError("Review Hub v7 could not find Technical tab")
    budget_tab = (
        '<button id="tab-budget" class="hub-tab" type="button" role="tab" aria-selected="false" '
        'aria-controls="panel-budget" data-tab="budget">Budget</button>\n'
    )
    document = document[:tab_at] + budget_tab + document[tab_at:]

    technical_panel = '<div id="panel-technical"'
    panel_at = document.find(technical_panel)
    if panel_at < 0:
        raise RuntimeError("Review Hub v7 could not find Technical panel")
    panel = (
        '<div id="panel-budget" class="hub-panel" role="tabpanel" aria-labelledby="tab-budget" data-panel="budget" hidden>'
        + budget_panel(snapshot)
        + '</div>\n'
    )
    document = document[:panel_at] + panel + document[panel_at:]
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
    pricing_path: Path | None = None,
) -> Path:
    index_path = _build_site_v6(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
    )
    resolved_pricing = pricing_path or Path(os.getenv("COST_PRICING_PATH", "config/cost_rates.json"))
    snapshot = build_cost_snapshot(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        output_dir=output_dir,
        pricing_path=resolved_pricing,
    )
    downloads = output_dir / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    (downloads / "cost_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    document = apply_budget_workspace(index_path.read_text(encoding="utf-8"), snapshot)
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
