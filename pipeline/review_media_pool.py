"""Small server-rendered pool status for Pages; no alternative media autoload."""
from __future__ import annotations
import html
import json
from pathlib import Path
from urllib.parse import urlsplit


def pool_panel(media_dir: Path) -> str:
    path = media_dir / 'media_pool_summary.json'
    esc = lambda value: html.escape(str(value), quote=True)
    if not path.is_file():
        return '<aside id="media-pool-status"><h3>Biblioteca multimedia</h3><p>Este episodio usa la adquisición anterior. La búsqueda documental integrada es optativa; su biblioteca se valida antes de asignar archivos.</p></aside>'
    summary = json.loads(path.read_text(encoding='utf-8'))
    labels = [('downloaded', 'Descargados'), ('eligible', 'Elegibles'), ('assigned', 'Asignados'),
              ('exact', 'Exactos por catálogo'), ('context', 'Contextuales'), ('low_resolution', 'Baja resolución')]
    metrics = ' · '.join(f'{label}: <strong>{esc(summary.get(key, 0))}</strong>' for key, label in labels)
    manifest_path = media_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else []
    rows = []
    for asset in manifest:
        provenance = asset.get('media_provenance')
        if not provenance:
            continue
        url = str(asset.get('source_url', ''))
        source = f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">Fuente</a>' if urlsplit(url).scheme in {'https', 'http'} else 'Fuente no enlazable'
        rows.append('<li>' + esc(asset.get('title') or asset.get('visual_query', '')) + ' — ' +
                    esc(asset.get('provider', '')) + ' · ' + esc(provenance['relation']) + ' · ' +
                    esc(f"{provenance['width']}×{provenance['height']}") + ' · ' + esc(asset.get('license', '')) +
                    ' · ' + source + '<br><small>' + esc(provenance['limitation']) + '</small></li>')
    unresolved = summary.get('unresolved_slots', [])
    audit_path = media_dir / 'media_cost_audit.json'
    cost = ''
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        cost = ('<p>Costo estimado de adquisición documental: <strong>USD ' +
                esc(f"{audit['estimated_known_usd']:.6f}") + '</strong>. Intentos sin costo calculable: ' +
                esc(audit['unpriced_attempts']) + '. No es una factura; excluye planificación editorial y otras ejecuciones.</p>')
    return ('<aside id="media-pool-status"><h3>Biblioteca multimedia</h3><p>Modo: ' + esc(summary['mode']) +
            '. Transcripción desactivada. Las coincidencias se respaldan en catálogo; no constituyen una verificación humana universal.</p><p>' + metrics +
            '</p>' + cost + '<p>Fuentes: ' + esc(', '.join(summary.get('providers', [])) or 'Sin resultados') +
            '. Espacios sin resolver: ' + esc(', '.join(map(str, unresolved)) or 'Ninguno') +
            '.</p><details><summary>Procedencia de los archivos asignados</summary><ul>' + ''.join(rows) +
            '</ul></details><p>Las alternativas permanecen en el artefacto del run; no se precargan en esta página.</p></aside>')


def inject_pool_panel(document: str, media_dir: Path) -> str:
    marker = '<section id="multimedia" data-search-group>'
    if marker in document:
        return document.replace(marker, marker + pool_panel(media_dir), 1)
    # Fail rather than silently publish a page without the requested integration view.
    raise ValueError('Review Hub multimedia section is missing')
