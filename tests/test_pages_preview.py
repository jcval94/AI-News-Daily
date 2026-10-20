from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from pipeline.pages_preview import SOURCE, _remote_assets, build_preview
from pipeline.review_hub_catalog import catalog_document


class PagesPreviewTests(unittest.TestCase):
    def test_snapshot_keeps_rejected_status_and_original_script(self):
        episodes = [dict(id=day, date=day, title='Original', status=status,
                         href=f'episodes/{day}/index.html') for day, status in
                    [('2026-10-16', 'No aprobado'), ('2026-09-25', 'Aprobado')]]
        catalog = catalog_document(episodes, current_id='2026-09-25')
        page = '<html><head></head><body><h1>Título real</h1><div id="scriptText">Hechos &amp; dudas</div></body></html>'
        runtime = 'const template = \'<a href="media/sample.png">Original</a>\';'
        def published(url):
            return catalog if url == SOURCE else runtime if url.endswith('memory.js') else page
        with tempfile.TemporaryDirectory() as tmp, patch('pipeline.pages_preview._download_text', side_effect=published):
            root = Path(tmp)
            build_preview(root, source_sha='branch-sha')
            result = (root / 'index.html').read_text()
            self.assertIn('"status":"No aprobado"', result)
            self.assertIn('const DEFAULT_EPISODE="2026-09-25"', result)
            self.assertIn('Título real', result)
            self.assertIn('<div id="scriptText">Hechos &amp; dudas</div>', (root / episodes[0]['href']).read_text())
            provenance = json.loads((root / 'preview-provenance.json').read_text())
            self.assertEqual(provenance['branch_commit'], 'branch-sha')
            self.assertEqual(provenance['episode_count'], 2)
            self.assertEqual(len(provenance['source_file_sha256']), 8)
            self.assertEqual((root / 'memory/memory.js').read_text(), runtime)

    def test_untrusted_catalog_cannot_redirect_preview_downloads(self):
        for href in ('https://other.example/private', 'episodes/../index.html', 'episodes/2026-09-25/index.html?token=x'):
            with self.subTest(href=href), tempfile.TemporaryDirectory() as tmp:
                catalog = catalog_document([dict(id='2026-09-25', href=href)], current_id='2026-09-25')
                with patch('pipeline.pages_preview._download_text', return_value=catalog) as download:
                    with self.assertRaises(ValueError):
                        build_preview(Path(tmp) / 'site')
                    download.assert_called_once_with(SOURCE)
                    self.assertFalse((Path(tmp) / 'site').exists())

    def test_resource_rewriting_preserves_script_evidence_and_spoken_text(self):
        source = ('<html><script type="application/json">{"sample":"<a href=\'media/a.png\'>evidencia</a>"}</script>'
                  '<div id="scriptText">Texto &lt;a href="media/a.png"&gt;</div>'
                  '<img src="media/a.png"><video poster="media/poster.jpg"><source data-src="media/a.mp4"></video>'
                  '<a href="#guion">Guion</a><a href="https://external.example/">Fuente</a></html>')
        result = _remote_assets(source, SOURCE + 'episodes/2026-09-25/index.html')
        self.assertIn('"sample":"<a href=\'media/a.png\'>evidencia</a>"', result)
        self.assertIn('<div id="scriptText">Texto &lt;a href="media/a.png"&gt;</div>', result)
        self.assertIn('src="' + SOURCE + 'episodes/2026-09-25/media/a.png"', result)
        self.assertIn('data-src="' + SOURCE + 'episodes/2026-09-25/media/a.mp4"', result)
        self.assertIn('<a href="#guion">Guion</a>', result)
        self.assertIn('href="https://external.example/"', result)
        self.assertEqual(_remote_assets(result, SOURCE), result)
        navigation = '<script src="memory.js" defer></script><a href="../index.html?view=health">Salud</a><a href="cases/workbench.html">Mesa</a>'
        linked = _remote_assets(navigation, SOURCE + 'memory/index.html')
        self.assertIn('<script src="memory.js" defer></script>', linked)
        self.assertIn('href="../index.html?view=health"', linked)
        self.assertIn('href="' + SOURCE + 'memory/cases/workbench.html"', linked)
