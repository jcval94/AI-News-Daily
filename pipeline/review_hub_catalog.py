from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path
from typing import Any


CATALOG_CSS = r"""
body .catalog-shell,body .episode-sidebar,body .episode-stage{height:100dvh}
body .episode-sidebar{--muted:#a3b3c4}
body .sidebar-head{padding:20px 18px 14px}body .sidebar-head h1{font-size:21px;line-height:1.2}
body .health-nav-wrap{gap:4px;padding:10px}
body .repo-health-link{padding:10px 12px;border-radius:9px;min-height:44px;background:transparent;border-color:transparent}
body .repo-health-link strong{font-size:14px}body .repo-health-link span,body .repo-health-link small{display:none}
body .episode-search-wrap{border-top:1px solid var(--line);padding:12px}
body .episode-search{font-size:14px;min-height:44px}
body .episode-list{padding-top:0}body .episode-item{padding:12px;gap:5px 8px}
body .episode-item strong{font-size:13px;line-height:1.45}body .episode-item small{font-size:12px}
body .episode-cost{font-size:11px}body .episode-stage{display:grid;grid-template-rows:auto auto minmax(0,1fr)}
body .episode-frame{height:100%;min-height:0;grid-row:3}.mobile-switcher{grid-row:1}
.catalog-context{grid-row:2}
.catalog-context{padding:10px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;border-bottom:1px solid var(--line);background:#0d1721;font-size:13px;line-height:1.5}
.catalog-context strong{color:#e8f5ff}.catalog-context a{color:#9ee6ff;text-underline-offset:4px}
.catalog-context .context-links{display:flex;gap:14px;flex-wrap:wrap}
.catalog-context[hidden]{display:none}
.catalog-skip{position:fixed;top:8px;left:8px;z-index:100;transform:translateY(-180%);background:#7dd3fc;color:#09121c;padding:12px;border-radius:8px;font-weight:700}
.catalog-skip:focus{transform:none}
:where(a,button,select,input):focus-visible{outline:3px solid #7dd3fc;outline-offset:3px}
@media(max-width:760px){
  body .episode-stage{grid-template-rows:auto auto minmax(0,1fr)}
  body .mobile-switcher{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.3fr);gap:8px;padding:8px 12px}
  body .mobile-switcher label{font-size:11px;text-transform:none;letter-spacing:0;color:#b4c7d9}
  body .mobile-switcher select{font-size:14px;min-height:44px;width:100%;padding:8px;min-width:0}
  .catalog-context{padding:8px 12px;font-size:12px;gap:4px}
  .catalog-context .context-links{gap:14px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

CATALOG_JS = r"""
const globalSelect=document.getElementById('globalViewSelect');
const context=document.getElementById('catalogContext');
const contextTitle=document.getElementById('catalogContextTitle');
const newest=EPISODES[0];
const approved=EPISODES.find(item=>item.status==='Aprobado');
const validTabs=new Set(['overview','script','evidence','media','process','budget','technical']);
function updateCatalog(value){
  const episode=byId.get(value);
  globalSelect.value=episode?'__episodes__':value;
  document.getElementById('mobileEpisodeField').hidden=!episode;
  context.hidden=!episode;
  if(episode){
    contextTitle.textContent=episode.status==='Aprobado'?`Episodio aprobado · ${episode.date}`:`Intento de producción · ${episode.date} · ${episode.status}`;
    const latest=document.getElementById('latestAttemptLink');
    latest.textContent=`Último intento · ${newest.date}`;latest.href=`?episode=${encodeURIComponent(newest.id)}`;
    const canonical=document.getElementById('latestApprovedLink');canonical.hidden=!approved;
    if(approved){canonical.textContent=`Último aprobado · ${approved.date}`;canonical.href=`?episode=${encodeURIComponent(approved.id)}`;}
  }
  [healthLink,memoryLink,metricsLink,experimentsLink].forEach(link=>link?.setAttribute('aria-current',link.classList.contains('active')?'page':'false'));
}
globalSelect.addEventListener('change',()=>setSelection(globalSelect.value==='__episodes__'?DEFAULT_EPISODE:globalSelect.value));
['latestAttemptLink','latestApprovedLink'].forEach(id=>document.getElementById(id).addEventListener('click',event=>{
  if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();const url=new URL(event.currentTarget.href);setSelection(url.searchParams.get('episode'));
}));
// Sync the iframe's workspace into the shareable outer URL. Same-origin only.
frame.addEventListener('load',()=>{
  try{
    const child=frame.contentWindow;
    const sync=()=>{
      const loadedPath=child.location.pathname;
      const episode=EPISODES.find(item=>new URL(item.href,location.href).pathname===loadedPath);
      const globalViews=[['health','__health__'],['memory','__memory__'],['metrics','__metrics__'],['experiments','__experiments__']];
      const globalView=globalViews.find(([view])=>new URL(`${view}/index.html`,location.href).pathname===loadedPath);
      if(!episode&&!globalView)return;
      const selection=episode?episode.id:globalView[1];
      const tab=child.document.querySelector('[data-tab].active')?.dataset.tab;
      const url=new URL(location.href);
      url.searchParams.delete('episode');url.searchParams.delete('view');url.searchParams.delete('tab');
      if(episode){url.searchParams.set('episode',episode.id);if(validTabs.has(tab)&&tab!=='overview')url.searchParams.set('tab',tab);}
      else url.searchParams.set('view',globalView[0]);
      history.replaceState(null,'',url);
      // Back/Forward may navigate the iframe independently of the outer history.
      // Reconcile metadata with the document actually loaded, without loading again.
      if(select.value!==selection)setSelection(selection,{push:false,navigate:false});
    };
    child.document.addEventListener('click',()=>queueMicrotask(sync));
    child.document.addEventListener('keydown',()=>queueMicrotask(sync));
    child.document.addEventListener('input',()=>requestAnimationFrame(sync));
    child.addEventListener('pageshow',sync);
    child.addEventListener('popstate',sync);
    sync();
  }catch(_){/* Standalone navigation remains available if embedding is restricted. */}
});
document.getElementById('catalogSkip').addEventListener('click',()=>frame.focus());
"""


RUN_RE = re.compile(r"run-(\d+)")
STATUS_LABELS = {
    "SCRIPT_APPROVED": "Aprobado",
    "APPROVED": "Aprobado",
    "SCRIPT_NOT_APPROVED": "No aprobado",
    "NOT_APPROVED": "No aprobado",
}


def _site_version() -> str:
    sha = os.getenv("GITHUB_SHA", "").strip()
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    parts: list[str] = []
    if sha:
        parts.append(sha[:12])
    if run_id:
        parts.append(f"run-{run_id}")
    return "-".join(parts) or "local"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _first_text(payload: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _episode_title(episode_dir: Path) -> str:
    plan = _read_json(episode_dir / "artifacts" / "episode_plan.json", {})
    title = _first_text(
        plan,
        (
            "episode_title",
            "title",
            "topic",
            "angle",
            "thesis",
            "central_thesis",
        ),
    )
    if title:
        return title[:130]

    selected = _read_json(episode_dir / "artifacts" / "selected_news.json", [])
    if isinstance(selected, list) and selected:
        first = selected[0] if isinstance(selected[0], dict) else {}
        title = _first_text(first, ("title", "titulo", "headline"))
        if title:
            return title[:130]
    return "AI News Daily"


def _episode_run_id(episode_dir: Path) -> str:
    state = _read_json(episode_dir / "artifacts" / "run_state.json", {})
    run_id = _first_text(state, ("run_id", "source_run_id", "github_run_id"))
    if run_id:
        return run_id
    scripts_dir = episode_dir / "scripts"
    if scripts_dir.exists():
        for path in sorted(scripts_dir.glob("latest-*-run-*.txt"), reverse=True):
            match = RUN_RE.search(path.name)
            if match:
                return match.group(1)
    return ""


def _episode_status(episode_dir: Path) -> str:
    state = _read_json(episode_dir / "artifacts" / "run_state.json", {})
    reviews = _read_json(episode_dir / "artifacts" / "reviews.json", {})
    raw = _first_text(
        state,
        ("status", "gate_status", "script_status", "final_status"),
    ) or _first_text(
        reviews,
        ("status", "gate_status", "script_status", "final_status"),
    )
    if raw:
        return STATUS_LABELS.get(raw.upper(), raw.replace("_", " ").title())

    if isinstance(reviews, dict):
        approved = reviews.get("approved")
        if isinstance(approved, bool):
            return "Aprobado" if approved else "No aprobado"
    return "Disponible"


def _episode_cost(episode_dir: Path) -> float | None:
    snapshot = _read_json(episode_dir / "downloads" / "cost_snapshot.json", {})
    if not isinstance(snapshot, dict):
        return None
    totals = snapshot.get("totals", {})
    if not isinstance(totals, dict):
        return None
    value = totals.get("known_direct_cost_usd")
    try:
        return round(float(value), 8) if value is not None else None
    except (TypeError, ValueError):
        return None


def episode_metadata(episode_dir: Path) -> dict[str, Any]:
    episode_id = episode_dir.name
    return {
        "id": episode_id,
        "date": episode_id,
        "title": _episode_title(episode_dir),
        "run_id": _episode_run_id(episode_dir),
        "status": _episode_status(episode_dir),
        "known_direct_cost_usd": _episode_cost(episode_dir),
        "href": f"episodes/{episode_id}/index.html",
    }


def discover_episodes(episodes_root: Path) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    if not episodes_root.exists():
        return episodes
    for episode_dir in episodes_root.iterdir():
        if not episode_dir.is_dir() or not (episode_dir / "index.html").exists():
            continue
        episodes.append(episode_metadata(episode_dir))
    episodes.sort(key=lambda item: str(item.get("date") or item.get("id") or ""), reverse=True)
    return episodes


def _usd(value: Any) -> str:
    try:
        if value is None:
            return "—"
        return f"${float(value):.3f}"
    except (TypeError, ValueError):
        return "—"


def _episode_items(episodes: list[dict[str, Any]], current_id: str) -> str:
    items: list[str] = []
    for episode in episodes:
        episode_id = str(episode["id"])
        active = episode_id == current_id
        title = str(episode.get("title") or "AI News Daily")
        status = str(episode.get("status") or "Disponible")
        run_id = str(episode.get("run_id") or "")
        meta = " · ".join(part for part in (status, f"run {run_id}" if run_id else "") if part)
        items.append(
            f'<a class="episode-item{" active" if active else ""}" href="?episode={html.escape(episode_id, quote=True)}" '
            f'data-episode-id="{html.escape(episode_id, quote=True)}" aria-current="{"page" if active else "false"}">'
            f'<span class="episode-date">{html.escape(episode_id)}</span>'
            f'<strong>{html.escape(title)}</strong>'
            f'<small>{html.escape(meta)}</small>'
            f'<span class="episode-cost">{html.escape(_usd(episode.get("known_direct_cost_usd")))}</span>'
            '</a>'
        )
    return "".join(items)


def _select_options(episodes: list[dict[str, Any]], current_id: str) -> str:
    options = []
    for episode in episodes:
        episode_id = str(episode["id"])
        selected = " selected" if episode_id == current_id else ""
        options.append(
            f'<option value="{html.escape(episode_id, quote=True)}"{selected}>'
            f'{html.escape(episode_id)} · {html.escape(str(episode.get("status") or "Disponible"))}'
            '</option>'
        )
    return "".join(options)


def catalog_document(
    episodes: list[dict[str, Any]],
    *,
    current_id: str,
    site_version: str = "",
) -> str:
    if not episodes:
        raise ValueError("At least one episode is required to build the catalog")
    valid_ids = {str(item["id"]) for item in episodes}
    if current_id not in valid_ids:
        current_id = str(episodes[0]["id"])
    current = next(item for item in episodes if str(item["id"]) == current_id)
    site_version = (site_version or _site_version()).strip() or "local"
    payload = json.dumps(episodes, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    items = _episode_items(episodes, current_id)
    options = _select_options(episodes, current_id)
    frame_src = html.escape(str(current["href"]), quote=True)
    frame_title = html.escape(f"Review Hub — {current_id}", quote=True)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>AI News Daily · Episodios</title>
<style>
:root{{--bg:#080d13;--panel:#0d141d;--panel-2:#111b27;--line:#223043;--text:#eef6ff;--muted:#8395a8;--accent:#66d9ff;--ok:#57c49a;--sidebar:292px}}
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
body{{overflow:hidden}}.catalog-shell{{display:grid;grid-template-columns:var(--sidebar) minmax(0,1fr);height:100vh}}
.episode-sidebar{{position:relative;z-index:3;height:100vh;border-right:1px solid var(--line);background:linear-gradient(180deg,#0e1721 0%,#091019 100%);display:flex;flex-direction:column;min-width:0}}
.sidebar-head{{padding:22px 18px 14px;border-bottom:1px solid var(--line)}}.brand{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:800}}.sidebar-head h1{{font-size:22px;line-height:1.08;margin:7px 0 5px}}.sidebar-head p{{margin:0;color:var(--muted);font-size:12px;line-height:1.45}}
.health-nav-wrap{{padding:10px 10px 0;display:grid;gap:7px}}.repo-health-link{{display:grid;gap:3px;text-decoration:none;color:var(--text);padding:11px;border:1px solid #28445b;border-radius:12px;background:#102131}}.repo-health-link:hover,.repo-health-link.active{{background:#153047;border-color:#3d7897;box-shadow:inset 3px 0 0 var(--accent)}}.repo-health-link span{{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:850}}.repo-health-link strong{{font-size:12px}}.repo-health-link small{{font-size:10px;color:var(--muted)}}
.episode-search-wrap{{padding:12px 12px 7px}}.episode-search{{width:100%;border:1px solid var(--line);border-radius:11px;background:#0a1119;color:var(--text);padding:10px 11px;outline:none}}.episode-search:focus{{border-color:#3f8daf;box-shadow:0 0 0 3px #17405a55}}
.episode-list{{overflow:auto;padding:5px 8px 18px;display:grid;gap:5px}}.episode-item{{position:relative;display:grid;grid-template-columns:1fr auto;gap:3px 9px;text-decoration:none;color:var(--text);padding:12px 11px;border:1px solid transparent;border-radius:12px;background:transparent;transition:background .15s,border-color .15s}}.episode-item:hover{{background:#121d29;border-color:#213348}}.episode-item.active{{background:#132434;border-color:#2f5f7b;box-shadow:inset 3px 0 0 var(--accent)}}.episode-item[hidden]{{display:none}}
.episode-date{{grid-column:1;font-size:12px;font-weight:850;color:#c8d9e8;letter-spacing:.02em}}.episode-item strong{{grid-column:1 / -1;font-size:12px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.episode-item small{{grid-column:1;color:var(--muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.episode-cost{{grid-column:2;grid-row:1;font-size:10px;color:#9cd8ef;font-variant-numeric:tabular-nums}}
.sidebar-foot{{margin-top:auto;padding:10px 14px 14px;color:var(--muted);font-size:10px;border-top:1px solid var(--line)}}
.episode-stage{{min-width:0;height:100vh;background:#080d13}}.episode-frame{{display:block;width:100%;height:100vh;border:0;background:#080d13}}
.mobile-switcher{{display:none;padding:10px 12px;border-bottom:1px solid var(--line);background:#0d151f}}.mobile-switcher label{{display:block;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px}}.mobile-switcher select{{width:100%;padding:9px 10px;background:#0a1119;color:var(--text);border:1px solid var(--line);border-radius:10px}}
.empty-filter{{display:none;padding:16px;color:var(--muted);font-size:12px}}.empty-filter.show{{display:block}}
@media(max-width:760px){{body{{overflow:hidden}}.catalog-shell{{display:block;height:100vh}}.episode-sidebar{{display:none}}.episode-stage{{height:100vh;display:grid;grid-template-rows:auto 1fr}}.mobile-switcher{{display:block}}.episode-frame{{height:100%;min-height:0}}}}
{CATALOG_CSS}
</style>
</head>
<body>
<a id="catalogSkip" class="catalog-skip" href="#episodeFrame">Saltar al contenido</a>
<div class="catalog-shell">
  <aside class="episode-sidebar" aria-label="Selector de episodios">
    <div class="sidebar-head"><div class="brand">AI News Daily</div><h1>Revisión editorial</h1><p>Guiones, evidencia y producción.</p></div>
    <div class="health-nav-wrap"><a id="repoHealthLink" class="repo-health-link" href="?view=health"><span>Observabilidad</span><strong>Salud del repo</strong><small>CI · fuentes · producción · Pages</small></a><a id="memoryLink" class="repo-health-link" href="?view=memory"><span>Editorial memory</span><strong>Memoria editorial</strong><small>casos · mecanismos · uso · cooldown</small></a><a id="metricsLink" class="repo-health-link" href="?view=metrics"><span>Performance</span><strong>Métricas</strong><small>Editorial · Attention · Voice · SEO</small></a><a id="experimentsLink" class="repo-health-link" href="?view=experiments"><span>Laboratorio</span><strong>Experimentos</strong><small>historias · guiones · gates</small></a></div>
    <div class="episode-search-wrap"><input id="episodeSearch" class="episode-search" type="search" placeholder="Buscar episodio…" aria-label="Buscar episodio"></div>
    <nav id="episodeList" class="episode-list" aria-label="Episodios disponibles">{items}<div id="emptyFilter" class="empty-filter">No hay episodios que coincidan.</div></nav>
    <div class="sidebar-foot"><span id="episodeCount" role="status">{len(episodes)} episodio{'s' if len(episodes) != 1 else ''}</span> · costos en USD</div>
  </aside>
  <main class="episode-stage">
    <div class="mobile-switcher"><div><label for="globalViewSelect">Sección</label><select id="globalViewSelect"><option value="__episodes__">Episodios</option><option value="__health__">Salud del repo</option><option value="__memory__">Memoria editorial</option><option value="__metrics__">Métricas</option><option value="__experiments__">Experimentos</option></select></div><div id="mobileEpisodeField"><label for="episodeSelect">Episodio o intento</label><select id="episodeSelect">{options}</select></div></div>
    <div id="catalogContext" class="catalog-context"><strong id="catalogContextTitle">Episodio · {html.escape(current_id)}</strong><div class="context-links"><a id="latestAttemptLink" href="?episode={html.escape(str(episodes[0]['id']), quote=True)}">Último intento</a><a id="latestApprovedLink" href="?episode={html.escape(current_id, quote=True)}">Último aprobado</a></div></div>
    <iframe id="episodeFrame" class="episode-frame" src="{frame_src}" title="{frame_title}" loading="eager"></iframe>
  </main>
</div>
<script>
const EPISODES={payload};
const DEFAULT_EPISODE={json.dumps(current_id)};
const SITE_VERSION={json.dumps(site_version)};
const byId=new Map(EPISODES.map(item=>[item.id,item]));
const frame=document.getElementById('episodeFrame');
const select=document.getElementById('episodeSelect');
const links=[...document.querySelectorAll('[data-episode-id]')];
const search=document.getElementById('episodeSearch');
const emptyFilter=document.getElementById('emptyFilter');
const healthLink=document.getElementById('repoHealthLink');
const memoryLink=document.getElementById('memoryLink');
const metricsLink=document.getElementById('metricsLink');
const experimentsLink=document.getElementById('experimentsLink');

function cacheBustedPath(path){{
  const url=new URL(path,window.location.href);
  url.searchParams.set('v',`${{SITE_VERSION}}-${{Date.now().toString(36)}}`);
  return url.href;
}}

function selectedFromUrl(){{
  const params=new URLSearchParams(window.location.search);
  if(params.get('view')==='health') return '__health__';
  if(params.get('view')==='memory') return '__memory__';
  if(params.get('view')==='metrics') return '__metrics__';
  if(params.get('view')==='experiments') return '__experiments__';
  const value=params.get('episode');
  return byId.has(value) ? value : DEFAULT_EPISODE;
}}
function setEpisode(id,{{push=true,navigate=true}}={{}}){{
  if(!byId.has(id)) id=DEFAULT_EPISODE;
  const episode=byId.get(id);
  const source=new URL(episode.href,window.location.href);
  source.searchParams.set('v',SITE_VERSION);
  const tab=new URL(window.location.href).searchParams.get('tab');
  const requestedTab=validTabs.has(tab)?tab:'overview';
  if(requestedTab!=='overview') source.hash=requestedTab;
  const expected=source.href;
  let currentSource=new URL(frame.src||expected,window.location.href);
  let activeTab;
  try{{
    activeTab=frame.contentDocument?.querySelector('[data-tab].active');
    if(activeTab&&frame.contentWindow?.location?.href)currentSource=new URL(frame.contentWindow.location.href);
  }}catch(_){{}}
  currentSource.hash=source.hash;
  if(navigate&&(currentSource.href!==expected||!activeTab)){{
    if(frame.src!==expected) frame.src=expected;
  }}else if(navigate&&activeTab.dataset.tab!==requestedTab){{
    // Restore a history/deep-link tab through its existing runtime, keeping drafts.
    frame.contentDocument.querySelector(`[data-tab="${{requestedTab}}"]`)?.click();
  }}
  frame.title=`Review Hub — ${{episode.date}}`;
  if(select) select.value=id;
  if(healthLink) healthLink.classList.remove('active');
  if(memoryLink) memoryLink.classList.remove('active');
  if(metricsLink) metricsLink.classList.remove('active');
  if(experimentsLink) experimentsLink.classList.remove('active');
  links.forEach(link=>{{
    const active=link.dataset.episodeId===id;
    link.classList.toggle('active',active);
    link.setAttribute('aria-current',active?'page':'false');
  }});
  document.title=`${{episode.date}} · AI News Daily`;
  if(push){{
    const url=new URL(window.location.href);
    url.searchParams.delete('view');
    url.searchParams.set('episode',id);
    history.pushState({{episode:id}},'',url);
  }}
}}
function setHealth({{push=true,navigate=true}}={{}}){{
  const expected=cacheBustedPath('health/index.html');
  if(navigate&&frame.src!==expected) frame.src=expected;
  frame.title='Salud del repositorio';
  if(select) select.value='__health__';
  links.forEach(link=>{{link.classList.remove('active');link.setAttribute('aria-current','false');}});
  if(healthLink) healthLink.classList.add('active');
  if(memoryLink) memoryLink.classList.remove('active');
  if(metricsLink) metricsLink.classList.remove('active');
  if(experimentsLink) experimentsLink.classList.remove('active');
  document.title='Salud del repo · AI News Daily';
  if(push){{
    const url=new URL(window.location.href);
    url.searchParams.delete('episode');
    url.searchParams.set('view','health');
    history.pushState({{view:'health'}},'',url);
  }}
}}
function setMemory({{push=true,navigate=true}}={{}}){{
  const expected=cacheBustedPath('memory/index.html');
  if(navigate&&frame.src!==expected) frame.src=expected;
  frame.title='Narrative Memory';
  if(select) select.value='__memory__';
  links.forEach(link=>{{link.classList.remove('active');link.setAttribute('aria-current','false');}});
  if(healthLink) healthLink.classList.remove('active');
  if(memoryLink) memoryLink.classList.add('active');
  if(metricsLink) metricsLink.classList.remove('active');
  if(experimentsLink) experimentsLink.classList.remove('active');
  document.title='Narrative Memory · AI News Daily';
  if(push){{
    const url=new URL(window.location.href);
    url.searchParams.delete('episode');
    url.searchParams.set('view','memory');
    history.pushState({{view:'memory'}},'',url);
  }}
}}
function setMetrics({{push=true,navigate=true}}={{}}){{
  const expected=cacheBustedPath('metrics/index.html');
  if(navigate&&frame.src!==expected) frame.src=expected;
  frame.title='Histórico de métricas';
  if(select) select.value='__metrics__';
  links.forEach(link=>{{link.classList.remove('active');link.setAttribute('aria-current','false');}});
  if(healthLink) healthLink.classList.remove('active');
  if(memoryLink) memoryLink.classList.remove('active');
  if(metricsLink) metricsLink.classList.add('active');
  if(experimentsLink) experimentsLink.classList.remove('active');
  document.title='Histórico de métricas · AI News Daily';
  if(push){{
    const url=new URL(window.location.href);
    url.searchParams.delete('episode');
    url.searchParams.set('view','metrics');
    history.pushState({{view:'metrics'}},'',url);
  }}
}}
function setExperiments({{push=true,navigate=true}}={{}}){{
  const expected=cacheBustedPath('experiments/index.html');
  if(navigate&&frame.src!==expected) frame.src=expected;
  frame.title='Experimentos';
  if(select) select.value='__experiments__';
  links.forEach(link=>{{link.classList.remove('active');link.setAttribute('aria-current','false');}});
  if(healthLink) healthLink.classList.remove('active');
  if(memoryLink) memoryLink.classList.remove('active');
  if(metricsLink) metricsLink.classList.remove('active');
  if(experimentsLink) experimentsLink.classList.add('active');
  document.title='Experimentos · AI News Daily';
  if(push){{
    const url=new URL(window.location.href);
    url.searchParams.delete('episode');
    url.searchParams.set('view','experiments');
    history.pushState({{view:'experiments'}},'',url);
  }}
}}
function setSelection(value,options={{}}){{
  if(value==='__health__') setHealth(options);
  else if(value==='__memory__') setMemory(options);
  else if(value==='__metrics__') setMetrics(options);
  else if(value==='__experiments__') setExperiments(options);
  else setEpisode(value,options);
  updateCatalog(value);
}}
links.forEach(link=>link.addEventListener('click',event=>{{event.preventDefault();setSelection(link.dataset.episodeId);}}));
if(healthLink) healthLink.addEventListener('click',event=>{{event.preventDefault();setSelection('__health__');}});
if(memoryLink) memoryLink.addEventListener('click',event=>{{event.preventDefault();setSelection('__memory__');}});
if(metricsLink) metricsLink.addEventListener('click',event=>{{event.preventDefault();setSelection('__metrics__');}});
if(experimentsLink) experimentsLink.addEventListener('click',event=>{{event.preventDefault();setSelection('__experiments__');}});
if(select) select.addEventListener('change',()=>setSelection(select.value));
window.addEventListener('popstate',()=>setSelection(selectedFromUrl(),{{push:false}}));
if(search) search.addEventListener('input',()=>{{
  const q=search.value.trim().toLocaleLowerCase('es');
  let visible=0;
  links.forEach(link=>{{
    const hit=!q || link.textContent.toLocaleLowerCase('es').includes(q);
    link.hidden=!hit;
    if(hit) visible+=1;
  }});
  emptyFilter.classList.toggle('show',visible===0);
  document.getElementById('episodeCount').textContent=`${{visible}} de ${{links.length}} episodios`;
}});
{CATALOG_JS}
setSelection(selectedFromUrl(),{{push:false}});
</script>
</body>
</html>
"""


def build_catalog(
    *,
    episodes_root: Path,
    output_dir: Path,
    current_id: str | None = None,
    site_version: str | None = None,
) -> Path:
    episodes = discover_episodes(episodes_root)
    if not episodes:
        raise RuntimeError(f"No episode sites found under {episodes_root}")
    selected = current_id if current_id and any(item["id"] == current_id for item in episodes) else str(episodes[0]["id"])
    version = (site_version or _site_version()).strip() or "local"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "episodes.json").write_text(
        json.dumps(
            {
                "episodes": episodes,
                "default_episode": selected,
                "site_version": version,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    index_path = output_dir / "index.html"
    index_path.write_text(
        catalog_document(episodes, current_id=selected, site_version=version),
        encoding="utf-8",
    )
    return index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the multi-episode GitHub Pages shell")
    parser.add_argument("--episodes-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--current", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_catalog(
        episodes_root=Path(args.episodes_root),
        output_dir=Path(args.output_dir),
        current_id=str(args.current or "") or None,
    )
    print(result)


if __name__ == "__main__":
    main()
