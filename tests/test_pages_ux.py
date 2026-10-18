from __future__ import annotations

import json
from html import escape
from pathlib import Path
import shutil
import subprocess
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
            self.assertIn(b'data-review-ux="2"', first)

    def test_previous_presentation_version_is_replaced_without_duplicate_runtime(self):
        document = ('<html><head><style data-review-ux="1">old-css</style></head><body>'
                    '<div id="scriptText">Original</div><script type="application/json">{"publishable":false}</script>'
                    '<script>(()=>{const $ = selector => document.querySelector(selector);'
                    'const contexts={overview:[]};})();</script></body></html>')
        upgraded = enhance_review(document)
        self.assertNotIn('old-css', upgraded)
        self.assertEqual(upgraded.count('const contexts={overview:'), 1)
        self.assertEqual(upgraded.count('data-review-ux-runtime="2"'), 1)
        self.assertIn('<div id="scriptText">Original</div>', upgraded)
        self.assertIn('{"publishable":false}', upgraded)
        self.assertEqual(enhance_review(upgraded), upgraded)

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

    @unittest.skipUnless(shutil.which('node'), 'Node is optional for the browser-runtime contract')
    def test_episode_cache_version_changes_without_reloading_the_same_selection(self):
        episodes = [dict(id=day, date=day, title='Caso', status='Aprobado', href=f'episodes/{day}/index.html')
                    for day in ('2026-10-16', '2026-09-25')]
        document = catalog_document(episodes, current_id='2026-09-25', site_version='deployment-2')
        function = document[document.index('function setEpisode('):document.index('function setHealth(')]
        harness = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
let source='',writes=0;const frame={};
Object.defineProperty(frame,'src',{get:()=>source,set:value=>{source=value;writes++;}});
const context={URL,frame,SITE_VERSION:'deployment-2',DEFAULT_EPISODE:'2026-09-25',
  window:{location:{href:'https://example.test/hub/'}},select:{},document:{},links:[],
  healthLink:null,memoryLink:null,metricsLink:null,experimentsLink:null,
  byId:new Map(['2026-10-16','2026-09-25'].map(id=>[id,{id,date:id,href:`episodes/${id}/index.html`}]))};
vm.createContext(context);
vm.runInContext(FUNCTION,context);
context.setEpisode('2026-09-25',{push:false});
assert.equal(new URL(frame.src).searchParams.get('v'),'deployment-2');
context.setEpisode('2026-09-25',{push:false});
assert.equal(writes,1,'Selecting the same episode must preserve its current frame/draft');
context.setEpisode('2026-10-16',{push:false});
assert.equal(writes,2);
assert.equal(new URL(frame.src).pathname,'/hub/episodes/2026-10-16/index.html');
"""
        result = subprocess.run(['node', '-e', harness.replace('FUNCTION', json.dumps(function))], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
