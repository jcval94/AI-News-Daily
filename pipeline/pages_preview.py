"""Read-only design preview: branch presentation over a published Pages snapshot.

Never generates editorial content or publishes/promotes an episode. Large media
stays on the original Pages host; HTML and editorial statuses remain inspectable.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from pipeline.pages_ux import enhance_page
from pipeline.review_hub_catalog import _episode_title, catalog_document
from pipeline.review_hub_ux import enhance_review

SOURCE = 'https://jcval94.github.io/AI-News-Daily/'
MAX_HTML_BYTES = 12 * 1024 * 1024

RESPONSIVE_REVIEW = '''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión responsive del PR</title><style>
*{box-sizing:border-box}body{margin:0;background:#090d12;color:#edf1f5;font:14px system-ui}
header{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:16px;padding:16px;border-bottom:1px solid #29333f}
select,a{min-height:44px;padding:10px;color:#d0e6f2;background:#16212d;border:1px solid #45576a;border-radius:8px}
main{padding:16px;overflow:auto}iframe{display:block;margin:auto;height:800px;border:1px solid #45576a;background:#0b0f14;width:390px}
</style></head><body><header><strong>Revisión responsive del PR</strong>
<label for="viewportWidth">Ancho</label><select id="viewportWidth"><option>320</option><option selected>390</option><option>768</option></select>
<a href="index.html" target="_blank">Abrir aplicación</a></header>
<main><iframe id="viewport" src="index.html" title="Aplicación con el ancho seleccionado"></iframe></main>
<script>document.getElementById('viewportWidth').addEventListener('change',event=>{document.getElementById('viewport').style.width=event.target.value+'px';});</script>
</body></html>'''


def _download_text(url: str) -> str:
    for attempt in range(3):
        try:
            with urlopen(url, timeout=30) as response:
                data = response.read(MAX_HTML_BYTES + 1)
            if len(data) > MAX_HTML_BYTES:
                raise ValueError('Preview source exceeds the HTML size limit')
            return data.decode('utf-8')
        except OSError:
            if attempt == 2:
                raise
            time.sleep(.5 * (attempt + 1))
    raise AssertionError('Unreachable')


def _source_url(href: str) -> str:
    url = urljoin(SOURCE, href)
    base, target = urlsplit(SOURCE), urlsplit(url)
    if target.scheme != base.scheme or target.netloc != base.netloc or not target.path.startswith(base.path):
        raise ValueError('Preview sources must remain under the published Pages origin and path')
    if target.query or target.fragment:
        raise ValueError('Preview source paths must not include query strings or fragments')
    return url


def _remote_assets(document: str, page_url: str, local_paths: set[str] | None = None) -> str:
    # Only actual resource attributes are rewritten; script/evidence text is kept.
    pattern = r'(?P<prefix>\b(?:href|src|poster|data-src|data-lazy-src)=)(?P<quote>[\x22\x27])(?P<url>[^\x22\x27]*)(?P=quote)'
    if local_paths is None:
        local_paths = {'', 'index.html', 'memory/memory.js', *(f'{kind}/index.html' for kind in ('health', 'memory', 'metrics', 'experiments'))}

    def replace(match: re.Match[str]) -> str:
        value = html.unescape(match['url'])
        if not value or value.startswith(('#', '?', '//')) or urlsplit(value).scheme:
            return match[0]
        target = urljoin(page_url, value)
        target_path = urlsplit(target).path.removeprefix(urlsplit(SOURCE).path)
        if target_path in local_paths:
            return match[0]
        return match['prefix'] + match['quote'] + html.escape(target, quote=True) + match['quote']

    class ResourceAttributes(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=False)
            self.edits: list[tuple[int, int, str]] = []
            self.lines = [0] + [match.end() for match in re.finditer('\n', document)]

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            original = self.get_starttag_text()
            changed = re.sub(pattern, replace, original)
            if changed != original:
                row, column = self.getpos()
                start = self.lines[row - 1] + column
                self.edits.append((start, start + len(original), changed))

        handle_startendtag = handle_starttag

    parser = ResourceAttributes()
    parser.feed(document)
    for start, end, replacement in reversed(parser.edits):
        document = document[:start] + replacement + document[end:]
    return document


def build_preview(output_dir: Path, *, source_sha: str = 'local') -> Path:
    catalog = _download_text(SOURCE)
    payload = re.search(r'const EPISODES=(.*?);\s*const DEFAULT_EPISODE=(.*?);', catalog, re.S)
    if not payload:
        raise ValueError('Published catalog metadata not found')
    episodes, current_id = json.loads(payload[1]), json.loads(payload[2])
    if not isinstance(episodes, list) or not 1 <= len(episodes) <= 16:
        raise ValueError('Unexpected published episode inventory')
    tasks = []
    for episode in episodes:
        identifier = str(episode.get('id', ''))
        expected = f'episodes/{identifier}/index.html'
        if not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', identifier) or episode.get('href') != expected:
            raise ValueError('Unexpected published episode path')
        tasks.append((expected, 'episode'))
    identifiers = [episode['id'] for episode in episodes]
    if len(set(identifiers)) != len(identifiers) or current_id not in identifiers:
        raise ValueError('Published default episode or unique inventory is invalid')
    for kind in ('health', 'memory', 'metrics', 'experiments'):
        tasks.append((f'{kind}/index.html', kind))
    # Memory's existing controls live in a separate deferred runtime, not inline.
    tasks.append(('memory/memory.js', 'runtime'))
    local_paths = {'', 'index.html', *(path for path, _ in tasks)}

    def download(task: tuple[str, str]) -> tuple[str, str, str]:
        path, kind = task
        return path, kind, _download_text(_source_url(path))

    output_dir.mkdir(parents=True, exist_ok=True)
    hashes = {'index.html': hashlib.sha256(catalog.encode()).hexdigest()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for path, kind, original in pool.map(download, tasks):
            hashes[path] = hashlib.sha256(original.encode()).hexdigest()
            upgraded = original if kind == 'runtime' else enhance_review(original) if kind == 'episode' else enhance_page(original, kind)
            destination = output_dir / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            prepared = upgraded if kind == 'runtime' else _remote_assets(upgraded, _source_url(path), local_paths)
            destination.write_text(prepared, encoding='utf-8')
    for episode in episodes:
        episode['title'] = _episode_title(output_dir / 'episodes' / episode['id'])
    index = output_dir / 'index.html'
    index.write_text(catalog_document(episodes, current_id=current_id, site_version=source_sha), encoding='utf-8')
    (output_dir / 'responsive.html').write_text(RESPONSIVE_REVIEW, encoding='utf-8')
    provenance = dict(source=SOURCE, branch_commit=source_sha,
                      captured_at=datetime.now(timezone.utc).isoformat(),
                      episode_count=len(episodes), source_file_sha256=hashes,
                      media='Original public Pages resources; an internet connection is required.')
    (output_dir / 'preview-provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--source-sha', default='local')
    args = parser.parse_args()
    print(build_preview(args.output_dir, source_sha=args.source_sha))


if __name__ == '__main__':
    main()
