from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any


RUN_RE = re.compile(r"run-(\d+)")
STATUS_LABELS = {
    "SCRIPT_APPROVED": "Aprobado",
    "APPROVED": "Aprobado",
    "SCRIPT_NOT_APPROVED": "No aprobado",
    "NOT_APPROVED": "No aprobado",
}


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


def catalog_document(episodes: list[dict[str, Any]], *, current_id: str) -> str:
    if not episodes:
        raise ValueError("At least one episode is required to build the catalog")
    valid_ids = {str(item["id"]) for item in episodes}
    if current_id not in valid_ids:
        current_id = str(episodes[0]["id"])
    current = next(item for item in episodes if str(item["id"]) == current_id)
    payload = json.dumps(episodes, ensure_ascii=False, separators=(",", ":"))
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
.episode-search-wrap{{padding:12px 12px 7px}}.episode-search{{width:100%;border:1px solid var(--line);border-radius:11px;background:#0a1119;color:var(--text);padding:10px 11px;outline:none}}.episode-search:focus{{border-color:#3f8daf;box-shadow:0 0 0 3px #17405a55}}
.episode-list{{overflow:auto;padding:5px 8px 18px;display:grid;gap:5px}}.episode-item{{position:relative;display:grid;grid-template-columns:1fr auto;gap:3px 9px;text-decoration:none;color:var(--text);padding:12px 11px;border:1px solid transparent;border-radius:12px;background:transparent;transition:background .15s,border-color .15s}}.episode-item:hover{{background:#121d29;border-color:#213348}}.episode-item.active{{background:#132434;border-color:#2f5f7b;box-shadow:inset 3px 0 0 var(--accent)}}.episode-item[hidden]{{display:none}}
.episode-date{{grid-column:1;font-size:12px;font-weight:850;color:#c8d9e8;letter-spacing:.02em}}.episode-item strong{{grid-column:1 / -1;font-size:12px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}.episode-item small{{grid-column:1;color:var(--muted);font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.episode-cost{{grid-column:2;grid-row:1;font-size:10px;color:#9cd8ef;font-variant-numeric:tabular-nums}}
.sidebar-foot{{margin-top:auto;padding:10px 14px 14px;color:var(--muted);font-size:10px;border-top:1px solid var(--line)}}
.episode-stage{{min-width:0;height:100vh;background:#080d13}}.episode-frame{{display:block;width:100%;height:100vh;border:0;background:#080d13}}
.mobile-switcher{{display:none;padding:10px 12px;border-bottom:1px solid var(--line);background:#0d151f}}.mobile-switcher label{{display:block;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:5px}}.mobile-switcher select{{width:100%;padding:9px 10px;background:#0a1119;color:var(--text);border:1px solid var(--line);border-radius:10px}}
.empty-filter{{display:none;padding:16px;color:var(--muted);font-size:12px}}.empty-filter.show{{display:block}}
@media(max-width:760px){{body{{overflow:hidden}}.catalog-shell{{display:block;height:100vh}}.episode-sidebar{{display:none}}.episode-stage{{height:100vh;display:grid;grid-template-rows:auto 1fr}}.mobile-switcher{{display:block}}.episode-frame{{height:100%;min-height:0}}}}
</style>
</head>
<body>
<div class="catalog-shell">
  <aside class="episode-sidebar" aria-label="Selector de episodios">
    <div class="sidebar-head"><div class="brand">AI News Daily</div><h1>Episodios</h1><p>Selecciona un episodio y conserva el mismo Review Hub.</p></div>
    <div class="episode-search-wrap"><input id="episodeSearch" class="episode-search" type="search" placeholder="Buscar episodio…" aria-label="Buscar episodio"></div>
    <nav id="episodeList" class="episode-list" aria-label="Episodios disponibles">{items}<div id="emptyFilter" class="empty-filter">No hay episodios que coincidan.</div></nav>
    <div class="sidebar-foot"><span id="episodeCount">{len(episodes)} episodio{'s' if len(episodes) != 1 else ''}</span> · artifacts disponibles</div>
  </aside>
  <main class="episode-stage">
    <div class="mobile-switcher"><label for="episodeSelect">Episodio</label><select id="episodeSelect">{options}</select></div>
    <iframe id="episodeFrame" class="episode-frame" src="{frame_src}" title="{frame_title}" loading="eager"></iframe>
  </main>
</div>
<script>
const EPISODES={payload};
const DEFAULT_EPISODE={json.dumps(current_id)};
const byId=new Map(EPISODES.map(item=>[item.id,item]));
const frame=document.getElementById('episodeFrame');
const select=document.getElementById('episodeSelect');
const links=[...document.querySelectorAll('[data-episode-id]')];
const search=document.getElementById('episodeSearch');
const emptyFilter=document.getElementById('emptyFilter');

function selectedFromUrl(){{
  const value=new URLSearchParams(window.location.search).get('episode');
  return byId.has(value) ? value : DEFAULT_EPISODE;
}}
function setEpisode(id,{{push=true}}={{}}){{
  if(!byId.has(id)) id=DEFAULT_EPISODE;
  const episode=byId.get(id);
  const expected=new URL(episode.href,window.location.href).href;
  if(frame.src!==expected) frame.src=episode.href;
  frame.title=`Review Hub — ${{episode.date}}`;
  if(select) select.value=id;
  links.forEach(link=>{{
    const active=link.dataset.episodeId===id;
    link.classList.toggle('active',active);
    link.setAttribute('aria-current',active?'page':'false');
  }});
  document.title=`${{episode.date}} · AI News Daily`;
  if(push){{
    const url=new URL(window.location.href);
    url.searchParams.set('episode',id);
    history.pushState({{episode:id}},'',url);
  }}
}}
links.forEach(link=>link.addEventListener('click',event=>{{event.preventDefault();setEpisode(link.dataset.episodeId);}}));
if(select) select.addEventListener('change',()=>setEpisode(select.value));
window.addEventListener('popstate',()=>setEpisode(selectedFromUrl(),{{push:false}}));
if(search) search.addEventListener('input',()=>{{
  const q=search.value.trim().toLocaleLowerCase('es');
  let visible=0;
  links.forEach(link=>{{
    const hit=!q || link.textContent.toLocaleLowerCase('es').includes(q);
    link.hidden=!hit;
    if(hit) visible+=1;
  }});
  emptyFilter.classList.toggle('show',visible===0);
}});
setEpisode(selectedFromUrl(),{{push:false}});
</script>
</body>
</html>
"""


def build_catalog(*, episodes_root: Path, output_dir: Path, current_id: str | None = None) -> Path:
    episodes = discover_episodes(episodes_root)
    if not episodes:
        raise RuntimeError(f"No episode sites found under {episodes_root}")
    selected = current_id if current_id and any(item["id"] == current_id for item in episodes) else str(episodes[0]["id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "episodes.json").write_text(
        json.dumps({"episodes": episodes, "default_episode": selected}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    index_path = output_dir / "index.html"
    index_path.write_text(catalog_document(episodes, current_id=selected), encoding="utf-8")
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
