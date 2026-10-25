"""Static, offline-safe catalog browser for Pages; it never serves audio bytes."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from pipeline.audio_library import DEFAULT_CATALOG, load_catalog, rights_status

KIND_NAMES = {"music": "Música", "sfx": "Efectos", "transition": "Transiciones", "ambience": "Ambientes"}
MOOD_NAMES = {"calm": "Sereno", "curious": "Curioso", "tense": "Tensión",
              "hopeful": "Esperanza", "playful": "Lúdico",
              "dramatic": "Dramático", "neutral": "Neutro"}
RIGHTS_NAMES = {"approved": "Revisado", "review_required": "Pendiente", "blocked": "Bloqueado"}
INTENSITY_NAMES = {"low": "Baja", "medium": "Media", "high": "Alta"}

STYLE = """
:root{color-scheme:dark;--bg:#0b1016;--panel:#131c26;--line:#27374a;--text:#ebf1f8;--muted:#9daec0;--accent:#78cbe4}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}
main{max-width:1120px;margin:auto;padding:26px 18px 70px}a{color:var(--accent)}a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #8bdaf1;outline-offset:3px}
.back{display:inline-flex;padding:10px 0;text-decoration:none}.eyebrow{color:var(--accent);text-transform:uppercase;letter-spacing:.14em;font-size:11px;font-weight:700}
h1{font-size:clamp(28px,5vw,48px);letter-spacing:-.04em;line-height:1.15;margin:8px 0}h2{font-size:18px;margin:0}
.intro{color:var(--muted);max-width:690px;margin:12px 0 25px}.controls{padding:18px;background:var(--panel);border:1px solid var(--line);border-radius:16px}
input[type=search]{background:#0c141d;color:var(--text);border:1px solid #3c4e60;border-radius:10px;padding:13px 14px;width:100%;min-height:44px;font:inherit}
fieldset{border:0;padding:0;margin:15px 0 0}legend{font-weight:650;color:#cbd8e6;margin-bottom:7px;font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:7px}button{border:1px solid #385068;border-radius:999px;padding:10px 14px;min-height:44px;background:#1a2938;color:#d7e5f2;cursor:pointer;font:inherit;font-size:13px}
button[aria-pressed=true]{background:#c2eafa;color:#102532;border-color:#c2eafa;font-weight:700}
.results{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:28px 0 13px;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,285px),1fr));gap:12px}
article{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:19px;overflow-wrap:anywhere}
article[hidden]{display:none}.meta{font-size:12px;color:var(--muted);margin-top:7px}.tags{display:flex;flex-wrap:wrap;gap:7px;margin:13px 0}
.tags span{border:1px solid #355067;border-radius:5px;padding:2px 7px;font-size:11px;color:#c9dce9}
.rights{font-size:12px;font-weight:700}.rights.approved{color:#82d4b4}.rights.review_required{color:#f3c67a}.rights.blocked{color:#e69a9a}
.links{display:flex;flex-wrap:wrap;gap:13px;font-size:13px;margin-top:12px}
.empty{border:1px dashed #3b5064;border-radius:14px;padding:28px;color:var(--muted);background:var(--panel)}.note{font-size:12px;color:var(--muted)}
@media(max-width:520px){main{padding:16px 12px 40px}.controls{padding:13px}.results{margin-top:19px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

RUNTIME = """'use strict';
const cards=[...document.querySelectorAll('[data-audio-card]')];
const query=document.getElementById('audioSearch');
const counter=document.getElementById('audioCount');
const empty=document.getElementById('audioEmptyResults');
const filters={kind:'all',mood:'all',intensity:'all',provider:'all',rights:'all'};
function refresh(){
  const needle=query.value.trim().toLocaleLowerCase('es');
  let visible=0;
  for(const card of cards){
    const hit=Object.entries(filters).every(([k,v])=>v==='all'||card.dataset[k]===v);
    const matches=hit&&(!needle||card.textContent.toLocaleLowerCase('es').includes(needle));
    card.hidden=!matches;
    if(matches)visible++;
  }
  counter.textContent=visible+' de '+cards.length+' recursos';
  empty.hidden=visible!==0;
  empty.textContent=cards.length===0
    ? 'Todavía no hay pistas curadas. El catálogo está listo para recibir fuentes verificadas.'
    : 'Ningún recurso coincide con los filtros.';
}
for(const btn of document.querySelectorAll('button[data-filter-group]')){
  btn.addEventListener('click',()=>{
    const group=btn.dataset.filterGroup;
    if(!(group in filters))return;
    filters[group]=btn.dataset.value;
    for(const other of document.querySelectorAll('button[data-filter-group="'+group+'"]')){
      other.setAttribute('aria-pressed',String(other===btn));
    }
    refresh();
  });
}
query.addEventListener('input',refresh);
refresh();
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _link(url: str, title: str) -> str:
    return '<a href="' + _esc(url) + '" rel="noopener noreferrer" target="_blank">' + _esc(title) + '</a>'


def _chips(group: str, options: list[tuple[str, str]]) -> str:
    rendered = []
    for value, name in [("all", "Todos")] + options:
        rendered.append(
            '<button type="button" data-filter-group="' + _esc(group) +
            '" data-value="' + _esc(value) + '" aria-pressed="' +
            ("true" if value == "all" else "false") + '">' + _esc(name) + '</button>'
        )
    return '<fieldset><legend>' + _esc({
        "kind": "Tipo", "mood": "Emoción", "intensity": "Intensidad",
        "provider": "Fuente", "rights": "Derechos"
    }[group]) + '</legend><div class="chips">' + "".join(rendered) + '</div></fieldset>'


def _card(item: dict[str, Any]) -> str:
    decision = rights_status(item)
    tags = "".join("<span>" + _esc(tag) + "</span>" for tag in item["tags"])
    if item.get("mood"):
        tags += "<span>" + _esc(MOOD_NAMES.get(item["mood"], item["mood"])) + "</span>"
    duration = (str(round(item["duration_seconds"], 1)) + " s") if item.get("duration_seconds") else "Duración por verificar"
    attribution = item["license"].get("attribution_text", "")
    extra = ('<p class="note">Atribución: ' + _esc(attribution) + '</p>') if attribution else ""
    return (
        '<article data-audio-card data-kind="' + _esc(item["kind"]) +
        '" data-mood="' + _esc(item.get("mood", "")) +
        '" data-intensity="' + _esc(item["intensity"]) +
        '" data-provider="' + _esc(item["provider"]) +
        '" data-rights="' + _esc(decision) + '">'
        '<h2>' + _esc(item["title"]) + '</h2>'
        '<p class="meta">' + _esc(item["creator"]) + ' · ' + _esc(KIND_NAMES[item["kind"]]) +
        ' · ' + _esc(duration) + '</p><p class="meta">' +
        _esc(item["provider"]) + ' · ' + _esc(item["license"]["identifier"]) + '</p>'
        '<p class="rights ' + _esc(decision) + '">' + _esc(RIGHTS_NAMES[decision]) + '</p>'
        '<div class="tags">' + tags + '</div>' + extra +
        '<div class="links">' + _link(item["source_url"], "Ficha original") +
        _link(item["license"]["terms_url"], "Términos") +
        _link(item["license"]["evidence_url"], "Evidencia") + '</div></article>'
    )


def build_audio_library_page(*, catalog: Path = DEFAULT_CATALOG, output_dir: Path) -> Path:
    payload = load_catalog(catalog)
    items = payload["items"]
    providers = sorted({item["provider"] for item in items}, key=str.casefold)
    selectors = [
        _chips("kind", list(KIND_NAMES.items())),
        _chips("mood", list(MOOD_NAMES.items())),
        _chips("intensity", list(INTENSITY_NAMES.items())),
        _chips("provider", [(provider, provider) for provider in providers]),
        _chips("rights", list(RIGHTS_NAMES.items())),
    ]
    cards = "".join(_card(item) for item in items)
    document = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="dark">'
        '<title>Biblioteca sonora · AI News Daily</title>'
        '<style>' + STYLE + '</style></head>'
        '<body data-audio-library="v1"><main>'
        '<a class="back" href="../index.html">← Volver a episodios</a>'
        '<div class="eyebrow">AI News Daily · catálogo curado</div>'
        '<h1>Biblioteca sonora</h1>'
        '<p class="intro">Música, efectos, transiciones y ambientes. '
        'Metadatos y fuentes únicamente: aquí no se publica ni precarga audio. '
        'Las aprobaciones son revisiones documentadas, no garantías contra Content ID.</p>'
        '<section class="controls" aria-label="Filtros del catálogo">'
        '<label for="audioSearch">Buscar por título, creador o etiqueta</label>'
        '<input id="audioSearch" type="search" autocomplete="off" placeholder="Buscar sonido…">'
        + "".join(selectors) + '</section>'
        '<div class="results"><strong id="audioCount" role="status" aria-live="polite"></strong>'
        '<span>Audio físico: almacenamiento local</span></div>'
        '<section class="grid" id="audioGrid" aria-label="Recursos sonoros">' + cards + '</section>'
        '<p id="audioEmptyResults" class="empty" role="status"></p>'
        '<p class="note">Una pista pendiente o bloqueada no se utiliza automáticamente en producción.</p>'
        '</main><script src="audio.js" defer></script></body></html>'
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "index.html"
    path.write_text(document, encoding="utf-8")
    (output_dir / "audio.js").write_text(RUNTIME, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a safe, catalog-only music/SFX browser")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(build_audio_library_page(catalog=args.catalog, output_dir=args.output_dir))


if __name__ == "__main__":
    main()
