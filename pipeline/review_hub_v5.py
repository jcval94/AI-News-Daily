from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v4 import build_site as _build_site_v4
from pipeline.review_hub_v4 import derive_real_indicators


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _score(value: Any) -> str:
    try:
        if value is None or value == "":
            return "—"
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _search_text(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
        elif isinstance(value, (list, tuple, set)):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value or ""))
    return html.escape(" ".join(parts), quote=True)


def _section_bounds(document: str, section_id: str) -> tuple[int, int]:
    marker = f'<section id="{section_id}"'
    start = document.find(marker)
    if start < 0:
        raise RuntimeError(f"Review Hub v5 could not find #{section_id}")
    end = document.find("</section>", start)
    if end < 0:
        raise RuntimeError(f"Review Hub v5 could not find closing section for #{section_id}")
    return start, end + len("</section>")


def _pop_section(document: str, section_id: str) -> tuple[str, str]:
    start, end = _section_bounds(document, section_id)
    return document[start:end], document[:start] + document[end:]


def _status_badge(indicators: dict[str, Any]) -> str:
    publishable = indicators.get("publishable")
    if publishable is True:
        text, klass = "PUBLICABLE", "ok"
    elif publishable is False:
        text, klass = str(indicators.get("status") or "no_registrado").upper(), "bad"
    else:
        text, klass = "ESTADO NO REGISTRADO", "neutral"
    return f'<span class="badge {klass}">{html.escape(text)}</span>'


def _review_specs(reviews: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        ("Editorial", reviews.get("editorial", {}) if isinstance(reviews.get("editorial"), dict) else {}),
        ("Attention", reviews.get("youtube_attention_master", {}) if isinstance(reviews.get("youtube_attention_master"), dict) else {}),
        ("Voice", reviews.get("voice_humanity", {}) if isinstance(reviews.get("voice_humanity"), dict) else {}),
        ("SEO", reviews.get("seo_master", {}) if isinstance(reviews.get("seo_master"), dict) else {}),
    ]


def _primary_failures(reviews: dict[str, Any], *, limit: int = 3) -> list[dict[str, str]]:
    candidates: list[tuple[int, float, int, str, str]] = []
    for order, (label, review) in enumerate(_review_specs(reviews)):
        approved = review.get("approved")
        try:
            numeric_score = float(review.get("score"))
        except (TypeError, ValueError):
            numeric_score = 999.0
        notes = [str(item).strip() for item in (review.get("problems", []) or []) if str(item).strip()]
        if not notes:
            notes = [str(item).strip() for item in (review.get("improvements", []) or []) if str(item).strip()]
        if not notes and approved is False:
            notes = [f"{label} no aprobó el guion en esta iteración."]
        for note_index, note in enumerate(notes[:2]):
            candidates.append((0 if approved is False else 1, numeric_score, order * 10 + note_index, label, note))

    gate = reviews.get("gate", {}) if isinstance(reviews.get("gate"), dict) else {}
    checks = gate.get("checks", {}) if isinstance(gate.get("checks"), dict) else {}
    if checks.get("factuality_low") is False and not any("Factual" in note for *_, note in candidates):
        editorial = reviews.get("editorial", {}) if isinstance(reviews.get("editorial"), dict) else {}
        risk = str(editorial.get("factuality_risk") or "no bajo")
        candidates.append((0, -1.0, -1, "Factualidad", f"El gate exige riesgo factual bajo; el run registra riesgo {risk}."))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, _, _, label, note in candidates:
        key = " ".join(note.lower().split())
        if key in seen:
            continue
        seen.add(key)
        output.append({"label": label, "text": note})
        if len(output) >= limit:
            break
    return output


def _overview_html(indicators: dict[str, Any], reviews: dict[str, Any]) -> str:
    score_cards: list[str] = []
    for label, review in _review_specs(reviews):
        approved = review.get("approved")
        klass = "pass" if approved is True else "fail" if approved is False else "neutral"
        score_cards.append(
            f'<div class="score-card {klass}"><span>{html.escape(label)}</span>'
            f'<strong>{_score(review.get("score"))}</strong></div>'
        )

    failures = _primary_failures(reviews)
    if failures:
        failure_html = "".join(
            f'<li><span class="failure-label">{html.escape(item["label"])}</span>'
            f'<span>{html.escape(item["text"])}</span></li>'
            for item in failures
        )
    else:
        failure_html = '<li class="no-blockers">No hay bloqueos editoriales registrados.</li>'

    word_count = indicators.get("word_count")
    duration = indicators.get("duration_minutes")
    meta = []
    meta.append(f'{int(word_count):,} palabras' if isinstance(word_count, (int, float)) else "palabras —")
    meta.append(f'{float(duration):.1f} min estimados' if isinstance(duration, (int, float)) else "duración —")
    meta.append(f'run {html.escape(str(indicators.get("run_id") or "—"))}')

    return (
        '<section id="overview" class="overview" aria-labelledby="overview-title">'
        '<div class="overview-heading"><div><span class="eyebrow">Decisión editorial</span>'
        '<h2 id="overview-title">Resumen del episodio</h2></div>'
        f'<div class="overview-status">{_status_badge(indicators)}<span>{" · ".join(meta)}</span></div></div>'
        f'<div class="score-strip">{"".join(score_cards)}</div>'
        '<div class="decision-grid"><div class="decision-block"><h3>Qué necesita trabajo</h3>'
        f'<ol class="failure-list">{failure_html}</ol></div>'
        '<div class="decision-actions"><h3>Siguiente acción</h3>'
        '<p>Revisa el guion con los bloqueos editoriales visibles y vuelve a Technical solo si necesitas el detalle de ejecución.</p>'
        '<button class="button" type="button" data-open-tab="script">Revisar guion</button>'
        '<button class="button secondary" type="button" data-open-tab="technical">Ver diagnóstico completo</button>'
        '</div></div></section>'
    )


def _source_cards(selected: dict[str, Any]) -> str:
    items = selected.get("items", []) if isinstance(selected, dict) else []
    cards: list[str] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        title = html.escape(str(item.get("title") or "Sin título"))
        url = str(item.get("url") or "").strip()
        title_html = (
            f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noreferrer">{title}</a>'
            if url
            else title
        )
        quality = html.escape(str(item.get("url_quality") or "—"))
        source = html.escape(str(item.get("source") or "Fuente no registrada"))
        news_id = html.escape(str(item.get("news_id") or "—"))
        blob = _search_text(item)
        cards.append(
            f'<article class="source-card" data-source-mobile-item data-search-text="{blob}">'
            f'<div class="source-card-top"><span class="source-index">{index:02d}</span>'
            f'<span class="badge neutral">{quality}</span></div>'
            f'<h3>{title_html}</h3><p>{source}</p><small>ID · {news_id}</small></article>'
        )
    return '<div class="source-cards" aria-label="Fuentes seleccionadas en formato móvil">' + "".join(cards) + "</div>"


def _replace_search_dock(document: str) -> str:
    start = document.find('<section class="search-dock"')
    if start < 0:
        raise RuntimeError("Review Hub v5 could not find search dock")
    end = document.find("</section>", start)
    if end < 0:
        raise RuntimeError("Review Hub v5 could not find search dock closing tag")
    end += len("</section>")
    replacement = '''<section class="workspace-nav" aria-label="Navegación principal del Review Hub">
<nav class="hub-tabs" role="tablist" aria-label="Secciones del Review Hub">
<button id="tab-overview" class="hub-tab active" type="button" role="tab" aria-selected="true" aria-controls="panel-overview" data-tab="overview">Overview</button>
<button id="tab-script" class="hub-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-script" data-tab="script">Script</button>
<button id="tab-evidence" class="hub-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-evidence" data-tab="evidence">Evidence</button>
<button id="tab-media" class="hub-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-media" data-tab="media">Media</button>
<button id="tab-technical" class="hub-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-technical" data-tab="technical">Technical</button>
</nav>
<div class="search-row"><input id="globalSearch" type="search" autocomplete="off" enterkeyhint="search" placeholder="Buscar en el Review Hub…" aria-label="Buscar en el review hub"><span id="searchCount" class="search-count" aria-live="polite">Busca en todo el hub</span></div>
</section>'''
    return document[:start] + replacement + document[end:]


P0_CSS = r"""
/* v5 P0 information architecture: decision first, details on demand. */
.workspace-nav{position:sticky;top:8px;z-index:30;margin:18px 0 22px;padding:8px;border:1px solid #334258;border-radius:17px;background:#0d141ef2;backdrop-filter:blur(14px);box-shadow:0 12px 34px #0007}
.hub-tabs{display:flex;gap:5px;overflow-x:auto;overscroll-behavior-x:contain;scrollbar-width:thin;padding:1px 1px 7px}.hub-tab{appearance:none;border:1px solid transparent;border-radius:10px;background:transparent;color:#aebdcd;padding:8px 13px;font:inherit;font-size:13px;font-weight:760;cursor:pointer;white-space:nowrap}.hub-tab:hover{background:#152131;color:#eaf3fb}.hub-tab.active{background:#172a3b;border-color:#315271;color:#bfe9ff}.hub-tab:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.workspace-nav .search-row{border-top:1px solid #253348;padding-top:8px}.workspace-nav .search-row input{min-height:42px}
.hub-panel{min-height:280px}.hub-panel>section:first-child h2{margin-top:28px}.overview{padding:24px 0 8px}.overview-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:18px}.overview-heading h2{margin:4px 0 0}.overview-status{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:flex-end;color:var(--muted);font-size:12px}.score-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.score-card{min-height:92px;padding:14px 15px;border:1px solid var(--line);border-radius:15px;background:var(--panel)}.score-card span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}.score-card strong{display:block;font-size:30px;line-height:1.2;margin-top:6px}.score-card.fail{border-color:#583040;background:linear-gradient(180deg,#20151d,#151922)}.score-card.pass{border-color:#244c40;background:linear-gradient(180deg,#12241f,#151b21)}
.decision-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.8fr);gap:14px}.decision-block,.decision-actions{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:19px}.decision-block h3,.decision-actions h3{margin:0 0 12px}.failure-list{list-style:none;counter-reset:failures;margin:0;padding:0;display:grid;gap:9px}.failure-list li{counter-increment:failures;display:grid;grid-template-columns:102px 1fr;gap:12px;padding:11px 0;border-top:1px solid var(--line)}.failure-list li:first-child{border-top:0;padding-top:0}.failure-label{color:#ffb2c0;font-weight:800;font-size:12px;text-transform:uppercase;letter-spacing:.05em}.no-blockers{display:block!important;color:var(--muted)}.decision-actions p{color:var(--muted);margin-top:0}.decision-actions .button{border:0;cursor:pointer}.decision-actions .button.secondary{display:inline-block}
#panel-script #guion{max-width:850px;margin:0 auto}.hub-panel .script{max-height:none;overflow:visible}.hub-panel>section{margin-top:0}.hub-panel>section+section h2{margin-top:40px}
.source-cards{display:none}.source-card{background:var(--panel);border:1px solid var(--line);border-radius:15px;padding:15px}.source-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px}.source-index{font-weight:900;color:var(--accent);font-size:13px}.source-card h3{font-size:16px;line-height:1.35;margin:10px 0 7px}.source-card p{margin:0 0 5px;color:#c5d1de}.source-card small{color:var(--muted)}
#panel-technical #diagnostico h2{margin-top:28px}
.hero{padding:24px 28px}.hero h1{font-size:clamp(28px,4vw,46px);max-width:860px}.hero-actions{margin-top:14px}
@media(max-width:760px){
  .wrap{padding-left:13px;padding-right:13px}.hero{padding:19px 18px;border-radius:18px}.hero h1{font-size:29px}.lede{font-size:16px;line-height:1.55}.hero-meta{display:none}
  .workspace-nav{top:4px;margin:12px 0 16px;border-radius:14px;padding:7px}.hub-tabs{padding-bottom:6px}.hub-tab{min-height:40px;padding:8px 12px}.workspace-nav .search-row{display:grid;grid-template-columns:1fr}.workspace-nav .search-count{padding:0 3px}
  .overview{padding-top:14px}.overview-heading{align-items:flex-start;flex-direction:column;gap:10px}.overview-status{justify-content:flex-start}.score-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.score-card{min-height:82px}.score-card strong{font-size:26px}.decision-grid{grid-template-columns:1fr}.failure-list li{grid-template-columns:1fr;gap:3px}.decision-actions .button{width:100%;margin:4px 0;min-height:44px}
  #panel-evidence #fuentes .source-table{display:none}.source-cards{display:grid;gap:10px}.source-card{min-width:0}.source-card h3 a{overflow-wrap:anywhere}
  #panel-script #guion{max-width:none}.hub-panel .script{padding:19px 17px;font-size:16.5px;line-height:1.78}
}
"""


P0_JS = r"""
<script>
(() => {
  const tabs = Array.from(document.querySelectorAll('[data-tab]'));
  const panels = Array.from(document.querySelectorAll('.hub-panel[data-panel]'));
  const openButtons = Array.from(document.querySelectorAll('[data-open-tab]'));
  const sourceCards = Array.from(document.querySelectorAll('[data-source-mobile-item]'));
  const input = document.getElementById('globalSearch');
  const legacyTargets = {guion:'script', arquitectura:'evidence', beats:'evidence', fuentes:'evidence', diagnostico:'technical', multimedia:'media', historial:'technical', artefactos:'technical'};
  let active = 'overview';

  const norm = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();

  function activate(name, {focus=false, updateHash=true} = {}) {
    if (!panels.some(panel => panel.dataset.panel === name)) return;
    active = name;
    tabs.forEach(tab => {
      const selected = tab.dataset.tab === name;
      tab.classList.toggle('active', selected);
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    panels.forEach(panel => { panel.hidden = panel.dataset.panel !== name; });
    if (updateHash && history.replaceState) history.replaceState(null, '', '#' + name);
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab.dataset.tab, {updateHash:true}));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
      event.preventDefault();
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      activate(tabs[next].dataset.tab, {focus:true, updateHash:true});
    });
  });
  openButtons.forEach(button => button.addEventListener('click', () => activate(button.dataset.openTab, {updateHash:true})));

  function syncMobileSources() {
    if (!input) return;
    const q = norm(input.value);
    sourceCards.forEach(card => {
      const haystack = norm(card.dataset.searchText || card.textContent);
      card.hidden = Boolean(q) && !haystack.includes(q);
    });
  }

  if (input) {
    input.addEventListener('input', () => {
      syncMobileSources();
      const q = norm(input.value);
      if (!q) return;
      const firstMatchingPanel = panels.find(panel => {
        if (panel.dataset.panel === 'overview') return false;
        return Array.from(panel.querySelectorAll('[data-search-group]')).some(group => !group.hidden);
      });
      if (firstMatchingPanel && firstMatchingPanel.dataset.panel !== active) {
        activate(firstMatchingPanel.dataset.panel, {updateHash:false});
      }
    });
  }

  const rawHash = location.hash.replace('#','');
  const initial = panels.some(panel => panel.dataset.panel === rawHash) ? rawHash : legacyTargets[rawHash] || 'overview';
  activate(initial, {updateHash:false});
  if (legacyTargets[rawHash]) {
    requestAnimationFrame(() => document.getElementById(rawHash)?.scrollIntoView({block:'start'}));
  }
})();
</script>
"""


def apply_p0_information_architecture(
    document: str,
    *,
    indicators: dict[str, Any],
    reviews: dict[str, Any],
    selected: dict[str, Any],
) -> str:
    document = document.replace("</style>", P0_CSS + "\n</style>", 1)
    document = document.replace(
        '<a class="skip-link" href="#guion">Saltar al guion</a>',
        '<a class="skip-link" href="#overview">Saltar al resumen</a>',
        1,
    )
    document = _replace_search_dock(document)

    sections: dict[str, str] = {}
    for section_id in ("guion", "arquitectura", "beats", "diagnostico", "fuentes", "multimedia", "historial", "artefactos"):
        sections[section_id], document = _pop_section(document, section_id)

    sources = sections["fuentes"].replace('<div class="table-wrap">', '<div class="table-wrap source-table">', 1)
    sources = sources[:-len("</section>")] + _source_cards(selected) + "</section>"

    panels = (
        '<div id="panel-overview" class="hub-panel" role="tabpanel" aria-labelledby="tab-overview" data-panel="overview">'
        + _overview_html(indicators, reviews)
        + '</div>'
        + '<div id="panel-script" class="hub-panel" role="tabpanel" aria-labelledby="tab-script" data-panel="script" hidden>'
        + sections["guion"]
        + '</div>'
        + '<div id="panel-evidence" class="hub-panel" role="tabpanel" aria-labelledby="tab-evidence" data-panel="evidence" hidden>'
        + sections["arquitectura"] + sections["beats"] + sources
        + '</div>'
        + '<div id="panel-media" class="hub-panel" role="tabpanel" aria-labelledby="tab-media" data-panel="media" hidden>'
        + sections["multimedia"]
        + '</div>'
        + '<div id="panel-technical" class="hub-panel" role="tabpanel" aria-labelledby="tab-technical" data-panel="technical" hidden>'
        + sections["diagnostico"] + sections["historial"] + sections["artefactos"]
        + '</div>'
    )

    no_results = document.find('<div id="noResults"')
    if no_results < 0:
        raise RuntimeError("Review Hub v5 could not find no-results marker")
    insertion = document.find("</div>", no_results)
    if insertion < 0:
        raise RuntimeError("Review Hub v5 could not find no-results closing tag")
    insertion += len("</div>")
    document = document[:insertion] + "\n" + panels + document[insertion:]
    document = document.replace("</body>", P0_JS + "\n</body>", 1)
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
    index_path = _build_site_v4(
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
    reviews = _read_json(episode_dir / "reviews.json", {})
    selected = _read_json(episode_dir / "selected_news.json", {})
    document = apply_p0_information_architecture(
        index_path.read_text(encoding="utf-8"),
        indicators=indicators,
        reviews=reviews if isinstance(reviews, dict) else {},
        selected=selected if isinstance(selected, dict) else {},
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
