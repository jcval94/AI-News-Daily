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
        function += document[document.index('const globalSelect='):document.index("globalSelect.addEventListener")]
        harness = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
let source='about:blank',writes=0,active='overview';const elements={};
const frame={contentDocument:{querySelector:selector=>source==='about:blank'?null:selector==='[data-tab].active'
  ? {dataset:{tab:active}} : {click:()=>{active=selector.match(/data-tab="([^"]+)"/)[1];}}}};
Object.defineProperty(frame,'src',{get:()=>source,set:value=>{source=value;writes++;active=new URL(value).hash.slice(1)||'overview';}});
const context={URL,frame,SITE_VERSION:'deployment-2',DEFAULT_EPISODE:'2026-09-25',
  window:{location:{href:'https://example.test/hub/'}},select:{},
  document:{getElementById:id=>elements[id]??=( {} )},links:[],
  EPISODES:['2026-10-16','2026-09-25'].map(id=>({id,date:id,status:'Aprobado'})),
  healthLink:null,memoryLink:null,metricsLink:null,experimentsLink:null,
  byId:new Map(['2026-10-16','2026-09-25'].map(id=>[id,{id,date:id,href:`episodes/${id}/index.html`}]))};
vm.createContext(context);
vm.runInContext(FUNCTION,context);
context.location=context.window.location;
const selectEpisode=id=>{context.setEpisode(id,{push:false});context.updateCatalog(id);};
selectEpisode('2026-09-25');
assert.equal(new URL(frame.src).searchParams.get('v'),'deployment-2');
selectEpisode('2026-09-25');
assert.equal(writes,1,'Selecting the same episode must preserve its current frame/draft');
// The src attribute can differ from the child's active tab after its own navigation.
active='script';context.window.location.href='https://example.test/hub/?episode=2026-09-25&tab=script';
selectEpisode('2026-09-25');
selectEpisode('2026-09-25');
assert.equal(writes,1,'Repeated selection with an active tab must preserve the loaded document');
assert.equal(active,'script');
context.window.location.href='https://example.test/hub/?episode=2026-09-25&tab=evidence';
selectEpisode('2026-09-25');
assert.equal(active,'evidence','History must restore the requested tab through the existing runtime');
assert.equal(writes,1,'Restoring a tab must not reload the frame');
selectEpisode('2026-10-16');
assert.equal(writes,2);
assert.equal(new URL(frame.src).pathname,'/hub/episodes/2026-10-16/index.html');
assert.equal(new URL(frame.src).hash,'#evidence','A different episode must load directly into the requested tab');
selectEpisode('2026-10-16');
assert.equal(writes,2,'A src containing a deep-link hash must also be idempotent');
context.window.location.href='https://example.test/hub/?tab=invalid';
selectEpisode('2026-10-16');
assert.equal(active,'overview','Invalid tab names must fall back to the summary');
assert.equal(writes,2);
active='script';
context.setEpisode('2026-09-25',{push:false,navigate:false});
assert.equal(writes,2,'Reconciling the loaded iframe must only update catalog metadata');
assert.equal(active,'script');
assert.equal(context.select.value,'2026-09-25');
frame.contentWindow={location:{href:'https://example.test/hub/episodes/2026-09-25/index.html?v=deployment-2#script'}};
context.window.location.href='https://example.test/hub/?episode=2026-09-25&tab=script';
selectEpisode('2026-09-25');
assert.equal(writes,2,'A stale src attribute after iframe Back must not reload the actual document');
"""
        result = subprocess.run(['node', '-e', harness.replace('FUNCTION', json.dumps(function))], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is optional for the browser-runtime contract')
    def test_frame_history_reconciles_episode_identity_and_global_views(self):
        episodes = [dict(id=day, date=day, title='Caso', status='Aprobado', href=f'episodes/{day}/index.html')
                    for day in ('2026-10-16', '2026-09-25')]
        document = catalog_document(episodes, current_id='2026-09-25')
        start = document.index('const sync=()=>{')
        function = document[start:document.index("    child.document.addEventListener", start)]
        harness = r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
let url='https://example.test/hub/?episode=2026-10-16&tab=script',active='script',selection;
const context={URL,EPISODES:EPISODES,select:{value:'2026-10-16'},
  validTabs:new Set(['overview','script','evidence']),
  location:{href:url},history:{replaceState:(_,__,next)=>{url=String(next);context.location.href=url;}},
  child:{location:{pathname:'/hub/episodes/2026-09-25/index.html'},
    document:{querySelector:()=>({dataset:{tab:active}})}},
  setSelection:(id,options)=>{selection={id,options};context.select.value=id;}};
vm.createContext(context);vm.runInContext(FUNCTION+';this.syncFrame=sync;',context);
context.syncFrame();
assert.equal(new URL(url).searchParams.get('episode'),'2026-09-25','Back must label the document actually loaded');
assert.equal(new URL(url).searchParams.get('tab'),'script');
assert.equal(selection.id,'2026-09-25');assert.equal(selection.options.navigate,false);assert.equal(selection.options.push,false);
context.child.location.pathname='/hub/health/index.html';context.syncFrame();
assert.equal(new URL(url).searchParams.get('view'),'health');
assert.equal(new URL(url).searchParams.has('episode'),false);assert.equal(new URL(url).searchParams.has('tab'),false);
assert.equal(selection.id,'__health__');assert.equal(selection.options.navigate,false);
context.child.location.pathname='/hub/episodes/2026-10-16/index.html';active='overview';context.syncFrame();
assert.equal(new URL(url).searchParams.get('episode'),'2026-10-16');
assert.equal(new URL(url).searchParams.has('view'),false);assert.equal(new URL(url).searchParams.has('tab'),false);
const last=url;context.child.location.pathname='/unrecognized';context.syncFrame();assert.equal(url,last);
"""
        harness = harness.replace('EPISODES:EPISODES', 'EPISODES:' + json.dumps(episodes)).replace('FUNCTION', json.dumps(function))
        result = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
