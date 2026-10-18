from __future__ import annotations

from html import escape
from pathlib import Path
import tempfile
import unittest

from pipeline.pages_history import _patch_episode_site
from pipeline.pages_ux import enhance_page
from pipeline.review_hub_ux import enhance_review
from pipeline.review_hub_catalog import catalog_document


class PagesUXTests(unittest.TestCase):
    def test_upgrade_preserves_editorial_text_and_authoritative_state(self):
        # Labels may match spoken words; only tab labels should be translated.
        spoken = 'Script, Budget, Technical: <hechos> & "evidencia".'
        state = '{"status":"script_not_approved","publishable":false}'
        document = ('<html><head></head><body><button id="tab-script" data-tab="script">Script</button>'
                    '<div id="scriptText">' + escape(spoken) + '</div>'
                    '<script type="application/json">' + state + '</script></body></html>')
        upgraded = enhance_review(document)
        self.assertIn('>Guion</button>', upgraded)
        self.assertIn('<div id="scriptText">' + escape(spoken) + '</div>', upgraded)
        self.assertIn(state, upgraded)
        self.assertEqual(enhance_review(upgraded), upgraded)

    def test_recovered_history_is_upgraded_once_without_touching_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<html><body><div id="scriptText">Original</div></body></html>')
            (root / 'run_state.json').write_text('{"publishable":false}')
            _patch_episode_site(root)
            first = (root / 'index.html').read_bytes()
            _patch_episode_site(root)
            self.assertEqual(first, (root / 'index.html').read_bytes())
            self.assertEqual((root / 'run_state.json').read_text(), '{"publishable":false}')
            self.assertIn(b'data-review-ux="1"', first)

    def test_dashboard_upgrade_is_idempotent_and_keeps_evidence(self):
        document = '<html><head></head><body><table><td>Sin medir</td></table></body></html>'
        for kind in ('health', 'memory', 'metrics', 'experiments'):
            with self.subTest(kind=kind):
                upgraded = enhance_page(document, kind)
                self.assertEqual(enhance_page(upgraded, kind), upgraded)
                self.assertIn('<table><td>Sin medir</td></table>', upgraded)

    def test_catalog_titles_cannot_close_inline_script(self):
        title = '</script><script>alert(1)</script>'
        document = catalog_document([{'id': '2026-10-16', 'date': '2026-10-16', 'title': title,
                                     'href': 'episodes/2026-10-16/index.html', 'status': 'No aprobado'}], current_id='2026-10-16')
        self.assertNotIn(title, document)
        self.assertIn('\\u003c/script>', document)
        self.assertIn('id="globalViewSelect"', document)
        self.assertIn('id="episodeSelect"', document)


if __name__ == '__main__':
    unittest.main()
