from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v4 import derive_real_indicators
from pipeline.review_hub_v5 import build_site as _build_site_v5


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _section_bounds(document: str, section_id: str) -> tuple[int, int]:
    marker = f'<section id="{section_id}"'
    start = document.find(marker)
    if start < 0:
        raise RuntimeError(f"Review Hub v6 could not find #{section_id}")
    end = document.find("</section>", start)
    if end < 0:
        raise RuntimeError(f"Review Hub v6 could not find closing section for #{section_id}")
    return start, end + len("</section>")


def _panel_bounds(document: str, panel_id: str) -> tuple[int, int]:
    marker = f'<div id="{panel_id}"'
    start = document.find(marker)
    if start < 0:
        raise RuntimeError(f"Review Hub v6 could not find #{panel_id}")
    next_panel = document.find('<div id="panel-', start + len(marker))
    footer = document.find('<div class="footer">', start)
    end_candidates = [value for value in (next_panel, footer) if value >= 0]
    if not end_candidates:
        raise RuntimeError(f"Review Hub v6 could not find end of #{panel_id}")
    return start, min(end_candidates)


def _insert_after_opening_div(document: str, panel_id: str, fragment: str) -> str:
    start, _ = _panel_bounds(document, panel_id)
    opening_end = document.find(">", start)
    if opening_end < 0:
        raise RuntimeError(f"Review Hub v6 could not parse #{panel_id}")
    opening_end += 1
    return document[:opening_end] + fragment + document[opening_end:]


def _annotate_section(document: str, section_id: str, group: str, name: str, *, active: bool) -> str:
    start, _ = _section_bounds(document, section_id)
    opening_end = document.find(">", start)
    opening = document[start:opening_end]
    classes = " subpanel active" if active else " subpanel"
    if 'class="' in opening:
        opening = opening.replace('class="', f'class="{classes.strip()} ', 1)
    else:
        opening += f' class="{classes.strip()}"'
    opening += f' data-subpanel-group="{html.escape(group, quote=True)}" data-subpanel="{html.escape(name, quote=True)}"'
    return document[:start] + opening + document[opening_end:]


def _subtabs(group: str, specs: list[tuple[str, str]], *, label: str) -> str:
    buttons = []
    for index, (name, text) in enumerate(specs):
        selected = index == 0
        buttons.append(
            f'<button class="subtab{" active" if selected else ""}" type="button" '
            f'data-subtab-group="{html.escape(group, quote=True)}" data-subtab="{html.escape(name, quote=True)}" '
            f'aria-selected="{"true" if selected else "false"}">{html.escape(text)}</button>'
        )
    return (
        f'<nav class="subtabs" role="tablist" aria-label="{html.escape(label, quote=True)}">'
        + "".join(buttons)
        + "</nav>"
    )


def _compact_hero(document: str, indicators: dict[str, Any]) -> tuple[str, str]:
    row_start = document.find('<div class="hero-row">')
    if row_start < 0:
        raise RuntimeError("Review Hub v6 could not find hero row")
    row_end = document.find("</div>", row_start)
    if row_end < 0:
        raise RuntimeError("Review Hub v6 could not close hero row")
    row_end += len("</div>")

    publishable = indicators.get("publishable")
    if publishable is True:
        status_text, status_class = "PUBLICABLE", "ok"
    elif publishable is False:
        status_text, status_class = str(indicators.get("status") or "no_registrado").upper(), "bad"
    else:
        status_text, status_class = "ESTADO NO REGISTRADO", "neutral"
    episode = html.escape(str(indicators.get("episode_date") or "—"))
    run_id = html.escape(str(indicators.get("run_id") or "—"))
    compact_row = (
        '<div class="hero-row hero-row-compact">'
        f'<span class="badge {status_class}">{html.escape(status_text)}</span>'
        f'<span class="muted">Episodio {episode} · run {run_id}</span>'
        "</div>"
    )
    document = document[:row_start] + compact_row + document[row_end:]

    meta_start = document.find('<div class="hero-meta">')
    if meta_start < 0:
        return document, ""
    meta_end = document.find("</div>", meta_start)
    if meta_end < 0:
        return document, ""
    meta_end += len("</div>")
    meta_html = document[meta_start:meta_end]
    document = document[:meta_start] + document[meta_end:]
    return document, meta_html


def _add_search_controls(document: str) -> str:
    count_marker = '<span id="searchCount" class="search-count" aria-live="polite">Busca en todo el hub</span>'
    if count_marker not in document:
        raise RuntimeError("Review Hub v6 could not find search count")
    controls = (
        count_marker
        + '<button id="clearSearch" class="search-clear" type="button" aria-label="Limpiar búsqueda" hidden>Limpiar</button>'
        + '<kbd class="search-shortcut" aria-label="Atajo de búsqueda">/</kbd>'
    )
    return document.replace(count_marker, controls, 1)


def _enhance_evidence(document: str, plan: dict[str, Any], selected: dict[str, Any]) -> str:
    beats = plan.get("beats", []) if isinstance(plan, dict) else []
    evidence = plan.get("evidence", []) if isinstance(plan, dict) else []
    sources = selected.get("items", []) if isinstance(selected, dict) else []
    summary = (
        '<div class="panel-summary" aria-label="Resumen de evidencia">'
        f'<span><strong>{len(beats) if isinstance(beats, list) else 0}</strong> beats</span>'
        f'<span><strong>{len(evidence) if isinstance(evidence, list) else 0}</strong> evidencias</span>'
        f'<span><strong>{len(sources) if isinstance(sources, list) else 0}</strong> fuentes</span>'
        '</div>'
        + _subtabs(
            "evidence",
            [("architecture", "Arquitectura"), ("beats", "Beats"), ("sources", "Fuentes")],
            label="Vistas de Evidence",
        )
    )
    document = _insert_after_opening_div(document, "panel-evidence", summary)
    document = _annotate_section(document, "arquitectura", "evidence", "architecture", active=True)
    document = _annotate_section(document, "beats", "evidence", "beats", active=False)
    document = _annotate_section(document, "fuentes", "evidence", "sources", active=False)
    return document


def _enhance_technical(document: str, provenance_html: str) -> str:
    header = _subtabs(
        "technical",
        [("judges", "Jueces"), ("history", "Historial"), ("artifacts", "Artefactos")],
        label="Vistas técnicas",
    )
    if provenance_html:
        provenance = (
            '<details class="run-provenance"><summary>Provenance del run</summary>'
            f'<div class="run-provenance-body">{provenance_html}</div></details>'
        )
    else:
        provenance = ""
    document = _insert_after_opening_div(document, "panel-technical", header + provenance)
    document = _annotate_section(document, "diagnostico", "technical", "judges", active=True)
    document = _annotate_section(document, "historial", "technical", "history", active=False)
    document = _annotate_section(document, "artefactos", "technical", "artifacts", active=False)

    marker = '<p class="muted metric-provenance">'
    start = document.find(marker)
    if start >= 0:
        end = document.find("</p>", start)
        if end >= 0:
            end += len("</p>")
            paragraph = document[start:end]
            replacement = (
                '<details class="metric-provenance-details"><summary>Cómo se calcularon estos indicadores</summary>'
                + paragraph
                + '</details>'
            )
            document = document[:start] + replacement + document[end:]
    return document


def _annotate_media_cards(document: str, manifest: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    cards = [item for item in manifest if isinstance(item, dict) and str(item.get("file") or "").strip()]
    cards.sort(key=lambda value: float(value.get("start_seconds", 0) or 0))
    cursor = 0
    counts = {"total": 0, "opening": 0, "video": 0, "image": 0}
    for item in cards:
        marker = "<article class='media-card searchable-card'"
        start = document.find(marker, cursor)
        if start < 0:
            break
        tag_end = document.find(">", start)
        if tag_end < 0:
            break
        kind = "video" if (
            str(item.get("asset_type") or "").lower() == "video"
            or str(item.get("mime_type") or "").lower().startswith("video/")
            or str(item.get("file") or "").lower().endswith(".mp4")
        ) else "image"
        try:
            opening = float(item.get("start_seconds", 999)) < 20
        except (TypeError, ValueError):
            opening = False
        attrs = f" data-media-kind='{kind}' data-media-opening='{'true' if opening else 'false'}'"
        document = document[:tag_end] + attrs + document[tag_end:]
        cursor = tag_end + len(attrs) + 1
        counts["total"] += 1
        counts[kind] += 1
        if opening:
            counts["opening"] += 1
    return document, counts


def _enhance_media(document: str, manifest: list[dict[str, Any]]) -> str:
    document, counts = _annotate_media_cards(document, manifest)
    section_start, _ = _section_bounds(document, "multimedia")
    h2_end = document.find("</h2>", section_start)
    if h2_end < 0:
        raise RuntimeError("Review Hub v6 could not find multimedia heading")
    h2_end += len("</h2>")
    toolbar = (
        '<div class="media-toolbar" aria-label="Filtros de multimedia">'
        f'<span class="media-count"><strong>{counts["total"]}</strong> assets</span>'
        '<div class="media-filters" role="group" aria-label="Filtrar multimedia">'
        f'<button class="media-filter active" type="button" data-media-filter="all">Todo · {counts["total"]}</button>'
        f'<button class="media-filter" type="button" data-media-filter="opening">0–20s · {counts["opening"]}</button>'
        f'<button class="media-filter" type="button" data-media-filter="video">Video · {counts["video"]}</button>'
        f'<button class="media-filter" type="button" data-media-filter="image">Imagen · {counts["image"]}</button>'
        '</div></div>'
    )
    return document[:h2_end] + toolbar + document[h2_end:]


P1_CSS = r"""
/* v6 P1: hierarchy, scanability and focused review controls. */
.hero{padding:18px 22px}.hero h1{font-size:clamp(27px,3.6vw,42px);line-height:1.08;margin:.22em 0 .16em}.hero .lede{font-size:16.5px;line-height:1.55;margin-bottom:12px}.hero-row-compact{font-size:12px}.hero-actions{margin-top:10px}.hero-actions .button{padding:8px 12px;font-size:12px}
.workspace-nav{margin-top:12px}.search-row{position:relative}.search-clear{appearance:none;border:1px solid #334258;background:#192331;color:#d9e5f2;border-radius:9px;padding:7px 10px;font:inherit;font-size:12px;font-weight:750;cursor:pointer}.search-clear:hover{border-color:#46617f}.search-shortcut{display:inline-grid;place-items:center;min-width:30px;height:30px;border:1px solid #34445b;border-bottom-width:2px;border-radius:7px;background:#111a26;color:#9fb0c2;font:700 12px/1 ui-monospace,monospace}
.panel-summary{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 8px}.panel-summary span{display:inline-flex;gap:5px;align-items:baseline;border:1px solid var(--line);background:var(--panel);border-radius:999px;padding:6px 10px;color:var(--muted);font-size:12px}.panel-summary strong{color:var(--text);font-size:14px}
.subtabs{display:flex;gap:6px;overflow-x:auto;padding:5px 0 13px;border-bottom:1px solid var(--line);margin-bottom:6px}.subtab{appearance:none;border:1px solid #2c3b4e;background:#121a25;color:#b8c7d7;border-radius:9px;padding:7px 11px;font:inherit;font-size:12px;font-weight:780;cursor:pointer;white-space:nowrap}.subtab:hover{background:#182433}.subtab.active{background:#20354a;border-color:#3e6588;color:#dff4ff}.subtab:focus-visible,.media-filter:focus-visible,.search-clear:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.p1-enhanced .subpanel:not(.active){display:none!important}.hub-panel .subpanel h2{margin-top:22px}.source-table thead th{position:sticky;top:0;background:#151d2a;z-index:2}
.run-provenance{margin:14px 0 2px;border:1px solid var(--line);border-radius:12px;background:#0f151f}.run-provenance>summary,.metric-provenance-details>summary{cursor:pointer;padding:10px 13px;font-weight:760;color:#bdcddd;list-style:none}.run-provenance>summary::-webkit-details-marker,.metric-provenance-details>summary::-webkit-details-marker{display:none}.run-provenance-body{padding:0 13px 12px}.run-provenance .hero-meta{display:block;margin:0}.metric-provenance-details{margin:10px 0 16px;border:1px solid var(--line);border-radius:11px;background:#101722}.metric-provenance-details .metric-provenance{margin:0;padding:0 13px 12px}
.review-notes.collapsible:not(.expanded) li:nth-child(n+4){display:none}.review-notes-toggle{appearance:none;border:0;background:transparent;color:var(--accent);padding:3px 0;font:inherit;font-size:12px;font-weight:760;cursor:pointer}.review-notes-toggle:hover{text-decoration:underline}
.media-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:12px 0 10px}.media-count{color:var(--muted);font-size:12px}.media-count strong{color:var(--text);font-size:14px}.media-filters{display:flex;gap:6px;overflow-x:auto;max-width:100%;padding:2px 0}.media-filter{appearance:none;border:1px solid #2d3b4f;background:#121a25;color:#b9c9d9;border-radius:999px;padding:6px 10px;font:inherit;font-size:11px;font-weight:760;cursor:pointer;white-space:nowrap}.media-filter.active{background:#20364a;border-color:#3f688b;color:#e0f5ff}.media-card.media-filtered{display:none!important}
#panel-technical .grid2{gap:12px}#panel-technical .card{padding:16px}#panel-technical .review-notes{margin:8px 0;padding:8px 12px}#panel-technical .review-notes ul{margin-top:6px;padding-left:20px}
@media(max-width:760px){
  .hero{padding:16px}.hero h1{font-size:27px}.hero .lede{font-size:15.5px}.hero-actions{display:flex;gap:6px;overflow-x:auto}.hero-actions .button{flex:0 0 auto;min-height:38px;margin:0}
  .workspace-nav{position:sticky;top:3px}.search-shortcut{display:none}.search-clear{min-height:40px}.panel-summary{margin-top:12px}.subtabs{margin-bottom:2px}.subtab{min-height:39px}
  .media-toolbar{align-items:flex-start;flex-direction:column}.media-filters{width:100%}.media-filter{min-height:38px}
  #panel-technical .grid2{grid-template-columns:1fr}
}
"""


P1_JS = r"""
<script>
(() => {
  document.body.classList.add('p1-enhanced');
  const input = document.getElementById('globalSearch');
  const clear = document.getElementById('clearSearch');
  const subtabButtons = Array.from(document.querySelectorAll('[data-subtab]'));
  const subpanels = Array.from(document.querySelectorAll('[data-subpanel]'));
  const legacySubtargets = {arquitectura:'architecture', beats:'beats', fuentes:'sources', diagnostico:'judges', historial:'history', artefactos:'artifacts'};

  function activateSubtab(group, name, {focus=false} = {}) {
    subtabButtons.filter(button => button.dataset.subtabGroup === group).forEach(button => {
      const selected = button.dataset.subtab === name;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-selected', selected ? 'true' : 'false');
      button.tabIndex = selected ? 0 : -1;
      if (selected && focus) button.focus();
    });
    subpanels.filter(panel => panel.dataset.subpanelGroup === group).forEach(panel => {
      panel.classList.toggle('active', panel.dataset.subpanel === name);
    });
  }

  ['evidence','technical'].forEach(group => {
    const groupButtons = subtabButtons.filter(button => button.dataset.subtabGroup === group);
    groupButtons.forEach((button, index) => {
      button.addEventListener('click', () => activateSubtab(group, button.dataset.subtab));
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        let next = index;
        if (event.key === 'ArrowRight') next = (index + 1) % groupButtons.length;
        if (event.key === 'ArrowLeft') next = (index - 1 + groupButtons.length) % groupButtons.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = groupButtons.length - 1;
        activateSubtab(group, groupButtons[next].dataset.subtab, {focus:true});
      });
    });
  });

  const hashTarget = location.hash.replace('#','');
  if (legacySubtargets[hashTarget]) {
    const target = document.getElementById(hashTarget);
    const panel = target?.closest('[data-panel]');
    const group = panel?.dataset.panel;
    if (group === 'evidence' || group === 'technical') activateSubtab(group, legacySubtargets[hashTarget]);
  }

  function updateSearchControls() {
    if (!input || !clear) return;
    clear.hidden = !input.value;
  }
  if (input) {
    input.addEventListener('input', () => {
      updateSearchControls();
      if (!input.value.trim()) return;
      requestAnimationFrame(() => {
        ['evidence','technical'].forEach(group => {
          const candidates = subpanels.filter(panel => panel.dataset.subpanelGroup === group);
          const first = candidates.find(panel => !panel.hidden && Array.from(panel.querySelectorAll('[data-search-item]')).some(item => !item.hidden));
          if (first) activateSubtab(group, first.dataset.subpanel);
        });
      });
    });
  }
  if (clear && input) {
    clear.addEventListener('click', () => {
      input.value = '';
      input.dispatchEvent(new Event('input', {bubbles:true}));
      input.focus();
    });
  }
  updateSearchControls();

  document.querySelectorAll('.review-notes').forEach(notes => {
    const items = notes.querySelectorAll('li');
    if (items.length <= 3) return;
    notes.classList.add('collapsible');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'review-notes-toggle';
    const hiddenCount = items.length - 3;
    const refresh = () => { button.textContent = notes.classList.contains('expanded') ? 'Mostrar menos' : `Ver ${hiddenCount} más`; };
    button.addEventListener('click', () => { notes.classList.toggle('expanded'); refresh(); });
    notes.appendChild(button);
    refresh();
  });

  const mediaCards = Array.from(document.querySelectorAll('.media-card[data-media-kind]'));
  const mediaFilters = Array.from(document.querySelectorAll('[data-media-filter]'));
  function filterMedia(filter) {
    mediaFilters.forEach(button => button.classList.toggle('active', button.dataset.mediaFilter === filter));
    mediaCards.forEach(card => {
      const visible = filter === 'all'
        || (filter === 'opening' && card.dataset.mediaOpening === 'true')
        || card.dataset.mediaKind === filter;
      card.classList.toggle('media-filtered', !visible);
    });
  }
  mediaFilters.forEach(button => button.addEventListener('click', () => filterMedia(button.dataset.mediaFilter)));
})();
</script>
"""


def apply_p1_scanability(
    document: str,
    *,
    indicators: dict[str, Any],
    plan: dict[str, Any],
    selected: dict[str, Any],
    manifest: list[dict[str, Any]],
) -> str:
    document = document.replace("</style>", P1_CSS + "\n</style>", 1)
    document, provenance = _compact_hero(document, indicators)
    document = _add_search_controls(document)
    document = _enhance_evidence(document, plan, selected)
    document = _enhance_technical(document, provenance)
    document = _enhance_media(document, manifest)
    document = document.replace("</body>", P1_JS + "\n</body>", 1)
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
    index_path = _build_site_v5(
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
    plan = _read_json(episode_dir / "episode_plan.json", {})
    selected = _read_json(episode_dir / "selected_news.json", {})
    manifest = _read_json(media_dir / "manifest.json", [])
    document = apply_p1_scanability(
        index_path.read_text(encoding="utf-8"),
        indicators=indicators,
        plan=plan if isinstance(plan, dict) else {},
        selected=selected if isinstance(selected, dict) else {},
        manifest=manifest if isinstance(manifest, list) else [],
    )
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
