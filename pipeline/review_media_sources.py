"""Source filters for current and recovered Pages episodes, with no media requests."""
from __future__ import annotations

import html
import re
from collections import Counter
from typing import Any

from pipeline.media_origin import KINDS, source_origin

MARKER = 'id="media-origin-filters"'
CSS = '''<style id="media-origin-style">
.media-origin-panel{padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--panel);margin:12px 0}.media-origin-panel h3{margin:0 0 6px}.media-origin-panel p{color:var(--muted);font-size:12px;margin:8px 0}.media-origin-options{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.media-origin-options button{border:1px solid var(--line);border-radius:999px;background:var(--panel);color:var(--text);padding:8px 12px;font:inherit;font-size:12px;cursor:pointer;min-height:36px}.media-origin-options button[aria-pressed="true"]{background:#20364a;border-color:#699dbd;color:#e0f5ff}.media-origin-options button:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.media-source-badges{display:flex;flex-wrap:wrap;gap:5px}.media-source-badges span{border:1px solid var(--line);border-radius:6px;padding:3px 6px;font-size:11px;color:#bfe9ff}.media-source-badges .origin-local{color:#f0d3a5}.media-card.media-source-filtered{display:none!important}.media-origin-enabled #media-results{display:none}
</style>'''
JS = '''<script id="media-origin-script">
(() => {
  const root = document.getElementById('media-origin-filters');
  if (!root) return;
  document.body.classList.add('media-origin-enabled');
  const cards = Array.from(document.querySelectorAll('.media-card[data-origin-provider]'));
  const buttons = Array.from(root.querySelectorAll('[data-origin-filter]'));
  const selected = {provider: '', kind: ''};
  function refresh() {
    buttons.forEach(button => button.setAttribute('aria-pressed', String(selected[button.dataset.originFilter] === button.dataset.originValue)));
    let visible = 0;
    cards.forEach(card => {
      const matches = (!selected.provider || selected.provider === card.dataset.originProvider) && (!selected.kind || selected.kind === card.dataset.originKind);
      card.classList.toggle('media-source-filtered', !matches);
      if (matches && !card.hidden && !card.classList.contains('media-filtered')) visible++;
    });
    document.getElementById('media-origin-results').textContent = visible ? `${visible} de ${cards.length} recursos visibles` : 'Sin coincidencias. Cambia la fuente, el tipo o la búsqueda.';
  }
  // Bubbling runs after existing type/license/search handlers, so counts intersect all filters.
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-origin-filter]');
    if (button && root.contains(button)) selected[button.dataset.originFilter] = button.dataset.originValue;
    if (event.target.closest('#media-reset')) { selected.provider = ''; selected.kind = ''; }
    if (event.target.closest('#multimedia, #clearSearch')) refresh();
  });
  document.addEventListener('change', event => { if (event.target.closest('#multimedia')) refresh(); });
  document.addEventListener('input', event => { if (event.target.id === 'globalSearch') refresh(); });
  refresh();
})();
</script>'''


def upgrade_media_sources(document: str, manifest: list[dict[str, Any]]) -> str:
    """Idempotently backfill UI using file identity, not manifest/card ordering."""
    if MARKER in document or 'id="multimedia"' not in document:
        return document
    by_file = {str(a.get("file")): a for a in manifest if isinstance(a, dict) and a.get("file")}
    origins = []
    def card(match: re.Match) -> str:
        opening, _, body, closing = match.groups()
        link = re.search(r'''(?:src|href)=["']media/([^"']+)["']''', body)
        asset = by_file.get(html.unescape(link.group(1)), {}) if link else {}
        origin = source_origin(asset)
        origins.append(origin)
        attrs = f' data-origin-provider="{html.escape(origin["provider"], quote=True)}" data-origin-kind="{origin["kind"]}" data-origin-acquisition="{origin["acquisition"]}"'
        badge = '<div class="media-source-badges">' + f'<span>{html.escape(origin["label"])}</span><span class="origin-{origin["kind"]}">{KINDS[origin["kind"]]}</span>' + ('<span>Biblioteca documental</span>' if origin['acquisition'] == 'documentary_pool' else '') + '</div>'
        if '<div class="media-meta">' in body:
            body = body.replace('<div class="media-meta">', '<div class="media-meta">' + badge, 1)
        else:
            body += badge
        return opening[:-1] + attrs + '>' + body + closing
    document = re.sub(r'''(<article\b[^>]*class=(["'])[^"']*\bmedia-card\b[^"']*\2[^>]*>)(.*?)(</article>)''', card, document, flags=re.S)
    if not origins:
        return document
    counts = Counter(o['provider'] for o in origins)
    kinds = Counter(o['kind'] for o in origins)
    labels = {o['provider']: o['label'] for o in origins}
    def button(dimension: str, value: str, label: str, count: int) -> str:
        return f'<button type="button" data-origin-filter="{dimension}" data-origin-value="{html.escape(value, quote=True)}" aria-pressed="{str(not value).lower()}">{html.escape(label)} · {count}</button>'
    sources = button('provider', '', 'Todas las fuentes', len(origins)) + ''.join(button('provider', key, labels[key], counts[key]) for key in sorted(counts))
    types = button('kind', '', 'Todo origen', len(origins)) + ''.join(button('kind', key, KINDS[key], kinds[key]) for key in ('external', 'local', 'unknown') if kinds[key])
    documentary = sum(o['acquisition'] == 'documentary_pool' for o in origins)
    panel = f'<aside id="media-origin-filters" class="media-origin-panel"><h3>Fuente de los recursos</h3><div class="media-origin-options" role="group" aria-label="Filtrar por proveedor">{sources}</div><div class="media-origin-options" role="group" aria-label="Filtrar por origen externo o local">{types}</div><p>{documentary} recursos con procedencia de la biblioteca documental integrada registrada. Pexels y Wikimedia también son fuentes externas; los respaldos locales son tarjetas creadas por el sistema.</p><p id="media-origin-results" role="status" aria-live="polite"></p></aside>'
    # Supersede the old source select; keep license, relation and type controls intact.
    document = re.sub(r'<label>Fuente de origen<select\b[^>]*id="media-source"[^>]*>.*?</select></label>', '', document, count=1, flags=re.S)
    document = re.sub(r'(<section\b[^>]*id="multimedia"[^>]*>)', lambda m: m.group(1) + panel, document, count=1)
    return document.replace('</head>', CSS + '\n</head>', 1).replace('</body>', JS + '\n</body>', 1)
