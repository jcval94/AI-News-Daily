from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

from pipeline.media_pool import (Pool, DEFAULT_BUDGET, group_needs, safe_path, normalized_license,
                                 prepare_pool, finish_assignment, fingerprint, retrieval_mode)
from pipeline.media_dedup import asset_identity_keys, deduplicate_materialized_media, resolution_rank
from pipeline.licenses import assess_license
from pipeline.edit_manifest import _asset_payload
from pipeline.review_media_pool import inject_pool_panel


def segment(number=1, **extra):
    return {'mode':'media','slot_number':number,'visual_query':'Einstein','retrieval_subject':'Einstein',
            'visual_role':'evidence','start_seconds':number*5,'end_seconds':number*5+4, **extra}


def make_pool(root, segments=None):
    segments = segments or [segment()]
    return Pool(root, {'schema_version':1,'mode':'integrated','inputs':{},'budget':dict(DEFAULT_BUDGET),
        'needs':group_needs(segments, 'Einstein'), 'segments':segments, 'assets':[], 'diagnostics':[],
        'model_calls':0,'model_usage':[], 'transcript_mode':'off'})


def add(pool, path, *, ident='1', size=(400,240), rights='CC BY 4.0', relation='exact', color='navy'):
    Image.new('RGB', size, color).save(path)
    pool.add(path, {'source':'commons','id':ident,'url':'https://commons.wikimedia.org/w/index.php?curid='+ident,
                   'metadata':{'title':'Albert Einstein','license':rights,'creator':'Catalog author'}},
             pool.payload['needs'][0], relation=relation,
             evidence={'field':'title','quote':'Albert Einstein','value':'Albert Einstein'})


class MediaPoolTests(unittest.TestCase):
    def test_modes_fail_closed_and_default_off(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(retrieval_mode(), 'off')
        with patch.dict(os.environ, {'MEDIA_RETRIEVAL_MODE':'surprise'}):
            with self.assertRaises(ValueError): retrieval_mode()

    def test_provider_query_identity_and_incompatible_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for base,param in [('https://youtube.com/watch','v'),('https://commons.wikimedia.org/w/index.php','curid')]:
                a=asset_identity_keys({'source_url':base+'?'+param+'=1&utm_source=x'},media_root=root)
                b=asset_identity_keys({'source_url':base+'?'+param+'=2'},media_root=root)
                self.assertFalse(set(a)&set(b))
                self.assertEqual(a,asset_identity_keys({'source_url':base+'?'+param+'=1'},media_root=root))
            a=asset_identity_keys({'provider':'commons','provider_asset_id':'1','source_url':'https://commons.wikimedia.org/'},media_root=root)
            b=asset_identity_keys({'provider':'commons','provider_asset_id':'2','source_url':'https://commons.wikimedia.org/'},media_root=root)
            self.assertFalse(set(a)&set(b))

    def test_rights_normalization_does_not_turn_unknown_into_public_domain(self):
        for label in ['Fair use','CC BY-NC-ND 4.0','No restrictions','unknown','']:
            self.assertFalse(assess_license('commons',normalized_license(label))['allowed'])
        self.assertTrue(assess_license('archive',normalized_license('https://creativecommons.org/licenses/by/4.0/'))['allowed'])
        self.assertFalse(assess_license('archive',normalized_license('https://creativecommons.org/licenses/by-nc/4.0/'))['allowed'])

    def test_grouping_preserves_each_original_slot_and_grounding(self):
        needs=group_needs([segment(),segment(2),segment(3,retrieval_subject='Invented person')], 'Einstein')
        self.assertEqual(needs[0]['slots'],[1,2]); self.assertFalse(needs[1]['grounded'])
        different=group_needs([segment(),segment(2,retrieval_period='1987')], 'Einstein')
        self.assertEqual(len(different),2)

    def test_assignment_selects_later_high_resolution_distinct_identity_per_slot(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pool=make_pool(root/'pool',[segment(),segment(2)])
            add(pool,root/'low.png');add(pool,root/'high.png',size=(1280,720))
            record=pool.assign(segment(),root/'selected','beat')
            self.assertEqual(record['width'],1280)
            self.assertEqual(record['media_provenance']['relation'],'exact')
            self.assertTrue((root/'selected'/record['file']).is_file())
            self.assertIsNone(pool.assign(segment(2),root/'selected','beat'))
            self.assertEqual(len({a['source_asset_id'] for a in pool.payload['assets']}),1)
            self.assertEqual(len({a['rendition_id'] for a in pool.payload['assets']}),2)

    def test_ineligible_and_context_do_not_resolve_critical_cue(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pool=make_pool(root/'pool')
            add(pool,root/'fair.png',rights='Fair use')
            add(pool,root/'memorial.png',ident='2',relation='context',color='red')
            self.assertIsNone(pool.assign(segment(),root/'out','beat'))
            with patch.dict(os.environ,{'MEDIA_RETRIEVAL_MODE':'integrated'}):
                manifest=[]; result=finish_assignment(pool,manifest,[],[segment()],root/'out')
            self.assertEqual(len(result),1);self.assertEqual(result[0]['retrieval_status'],'unresolved')
            self.assertEqual(manifest,[])

    def test_corrupt_cache_cannot_replace_lower_valid_rendition(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pool=make_pool(root/'pool')
            add(pool,root/'low.png');add(pool,root/'high.png',size=(1280,720))
            (pool.root/pool.payload['assets'][1]['file']).write_bytes(b'broken')
            # Candidate validation precedes ranking so a bad high-res copy cannot suppress a good one.
            record=pool.assign(segment(),root/'out','beat')
            self.assertIsNotNone(record)
            self.assertEqual(record['width'],400)

    def test_relative_paths_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);bundle=root/'bundle';bundle.mkdir()
            (bundle/'escape').symlink_to(root,target_is_directory=True)
            for path in ['../x','/tmp/x','escape/x','a\\b']:
                with self.assertRaises(ValueError): safe_path(bundle,path)

    def test_stale_pool_and_offline_no_model(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'.pipeline-runs/2026-09-04/run'
            episode=root/'scripts/2026-09-04';episode.mkdir(parents=True)
            for name,value in [('script.txt','Einstein'),('episode_plan.json','{}'),('script_sections.json','{}'),('run_state.json','{"status":"approved"}')]:
                (episode/name).write_text(value)
            with patch.dict(os.environ,{'MEDIA_RETRIEVAL_MODE':'integrated'}), patch('pipeline.media_pool.subprocess.Popen') as process:
                pool=prepare_pool(episode,root/'multimedia/2026-09-04',[segment()],offline=True)
                process.assert_not_called()
                self.assertEqual(pool.payload['model_calls'],0)
                (episode/'script.txt').write_text('Changed script')
                with self.assertRaisesRegex(ValueError,'Stale'): prepare_pool(episode,root/'multimedia/2026-09-04',[segment()],offline=True)

    def test_provenance_blocks_context_even_if_record_claims_valid_license(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pool=make_pool(root/'pool');add(pool,root/'im.png')
            record=pool.assign(segment(),root/'out','beat')
            payload=_asset_payload(record,segment())
            self.assertTrue(payload['usable_for_edit'])
            record['media_provenance']['relation']='context'
            payload=_asset_payload(record,segment())
            self.assertFalse(payload['usable_for_edit']);self.assertIn('exact_identity_required',payload['blockers'])

    def test_pages_summary_escapes_catalogue_text_and_does_not_autoload_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'media_pool_summary.json').write_text(json.dumps({'mode':'integrated','downloaded':2,'eligible':1,'assigned':1,'providers':['<script>'],'unresolved_slots':[2]}))
            (root/'manifest.json').write_text('[]')
            html=inject_pool_panel('<section id="multimedia" data-search-group></section>',root)
            self.assertIn('Descargados',html); self.assertIn('&lt;script&gt;',html)
            self.assertNotIn('<video',html);self.assertNotIn('<img',html)
            self.assertNotIn('base64',html)

    def test_real_pixels_override_remote_proxy_metadata_and_corrupt_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);Image.new('RGB',(640,360)).save(root/'proxy.jpg')
            Image.new('RGB',(1280,720)).save(root/'better.jpg');(root/'bad.jpg').write_bytes(b'broken')
            proxy={'file':'proxy.jpg','source_width':3840,'source_height':2160}
            better={'file':'better.jpg','source_width':1280,'source_height':720}
            self.assertLess(resolution_rank(proxy,media_root=root),resolution_rank(better,media_root=root))
            self.assertEqual(resolution_rank({'file':'bad.jpg','source_width':8000,'source_height':4000},media_root=root),(0,0,0,0))


class MediaProvenanceHandoffTests(unittest.TestCase):
    def test_provenance_survives_virtual_timeline_otio_roundtrip_and_resolve(self):
        import opentimelineio as otio
        from test_virtual_timeline import recording_pack, edit_manifest
        from pipeline.virtual_timeline import build_virtual_timeline
        from pipeline.otio_export import build_otio_timeline, validate_roundtrip
        from pipeline.placeholder_media import build_placeholder_manifest
        from pipeline.resolve_bridge import build_resolve_plan, materialize_resolve_otio
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);pool=make_pool(root/'pool');add(pool,root/'source.png')
            selected=root/'multimedia/2026-09-24'
            record=pool.assign(segment(),selected,'beat')
            edit=edit_manifest()
            for cue in edit['timeline']:
                if cue.get('mode')=='media':
                    cue['media']=_asset_payload(record,segment())
            virtual=build_virtual_timeline(recording_pack=recording_pack(),edit_manifest=edit)
            clips=next(t for t in virtual['tracks'] if t['track_id']=='V2')['clips']
            self.assertEqual(clips[0]['source']['media_provenance'],record['media_provenance'])
            episode=root/'scripts/2026-09-24';episode.mkdir(parents=True)
            timeline=build_otio_timeline(virtual,output_dir=episode)
            source=episode/'timeline.otio'
            otio.adapters.write_to_file(timeline,str(source))
            reloaded=otio.adapters.read_from_file(str(source))
            validate_roundtrip(source_payload=virtual,timeline=reloaded)
            placeholder=episode/'placeholder_media';placeholder.mkdir()
            manifest=build_placeholder_manifest(virtual_timeline=virtual,output_dir=placeholder)
            plan=build_resolve_plan(virtual_timeline=virtual,placeholder_manifest=manifest,repo_root=root)
            target=episode/'resolve_timeline.otio'
            materialize_resolve_otio(plan=plan,source_otio_path=source,destination=target,repo_root=root)
            resolved=otio.adapters.read_from_file(str(target))
            selected_clips=[c for c in resolved.find_clips() if c.metadata.get('ai_news_daily',{}).get('track_id')=='V2']
            self.assertTrue(selected_clips)
            self.assertEqual(selected_clips[0].metadata['ai_news_daily']['source']['media_provenance']['rendition_id'],record['rendition_id'])
            self.assertEqual(selected_clips[0].source_range.start_time.value,0)
