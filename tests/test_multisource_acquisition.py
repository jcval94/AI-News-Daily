from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from PIL import Image

from pipeline.media_pool import Pool, prepare_pool, group_needs, finish_assignment, provider_report
from pipeline.media_origin import source_origin
from pipeline.media_http import public_json, _hosts
from test_media_pool import make_pool, add, segment


class MultisourceTests(unittest.TestCase):
    def test_context_cannot_replace_exact_reference(self):
        cue = segment(retrieval_subject='', visual_role='context', visual_query='laboratory')
        need = group_needs([cue], 'Science is discussed.')[0]
        self.assertTrue(need['grounded'])
        self.assertFalse(need['exact_required'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pool = make_pool(root / 'pool', [cue])
            add(pool, root / 'context.png', relation='context')
            self.assertTrue(pool.payload['assets'][0]['eligible'])
            self.assertIsNone(pool.assign(segment(), root / 'selected', 'beat'))
            record = pool.assign(cue, root / 'selected', 'beat')
            self.assertEqual(record['media_provenance']['relation'], 'context')

    def test_provider_diversity_prefers_unused_eligible_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pool = make_pool(root / 'pool', [segment(), segment(2)])
            add(pool, root / 'a.png', ident='1', size=(1280, 720))
            add(pool, root / 'b.png', ident='2', size=(1280, 720), color='red')
            add(pool, root / 'c.png', ident='3', size=(1280, 720), color='green')
            pool.payload['assets'][2]['provider'] = 'archive'
            self.assertEqual(pool.assign(segment(), root / 'out', 'beat')['provider'], 'commons')
            self.assertEqual(pool.assign(segment(2), root / 'out', 'beat')['provider'], 'archive')

    def test_review_isolation_does_not_make_rejected_episode_production(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / '.pipeline-runs/date/review-test'
            episode = root / 'scripts/date'
            episode.mkdir(parents=True)
            for name, value in [('script.txt','Einstein'), ('episode_plan.json','{}'),
                                ('script_sections.json','{}'), ('run_state.json','{"status":"script_not_approved"}')]:
                (episode / name).write_text(value)
            env = {'MEDIA_RETRIEVAL_MODE': 'integrated', 'MEDIA_ACQUISITION_PURPOSE': 'production'}
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(ValueError, 'approved'):
                    prepare_pool(episode, root / 'multimedia/date', [segment()], offline=True)
            with patch.dict(os.environ, {**env, 'MEDIA_ACQUISITION_PURPOSE': 'review'}):
                pool = prepare_pool(episode, root / 'multimedia/date', [segment()], offline=True)
                self.assertEqual(pool.payload['purpose'], 'review')
                with self.assertRaisesRegex(ValueError, 'isolated'):
                    prepare_pool(episode, Path(temporary) / 'canonical', [segment()], offline=True)
            (episode / 'run_state.json').write_text('{"status":"approved"}')
            with patch.dict(os.environ, env):
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    prepare_pool(episode, root / 'multimedia/date', [segment()], offline=True)

    def test_discovery_does_not_count_as_assigned_and_aliases_do_not_inflate(self):
        report = provider_report({'diagnostics': [{'discovery': [{'source':'archive','status':'ok','count':8}]}]},
                                 [{'provider':'wikipedia','license_valid':True}, {'provider':'commons','license_valid':True}])
        self.assertEqual(report['archive']['assigned'], 0)
        self.assertEqual(report['commons']['assigned'], 2)
        self.assertNotIn('wikipedia', report)

    def test_failed_image_download_tries_second_provider(self):
        from pipeline.media import download_shot_asset
        candidate = {'provider':'pexels','provider_asset_id':1,'license':'Pexels License',
                     'download_url':'https://images.pexels.com/a', 'relevance_score':1}
        alternate = {**candidate, 'provider':'commons', 'license':'CC BY 4.0', 'relevance_score':0.9}
        with tempfile.TemporaryDirectory() as temporary, patch('pipeline.media.search_pexels', return_value=candidate), patch('pipeline.media.search_wikimedia', return_value=alternate), patch('pipeline.media._download_bytes', side_effect=[RuntimeError('blocked'), b'jpeg']), patch('pipeline.media._save_as_jpeg'), patch('pipeline.media.make_fallback_card') as fallback:
            result = download_shot_asset({'visual_query':'Einstein','shot_number':1}, Path(temporary)/'a.jpg')
            self.assertEqual(result['provider'], 'commons')
            fallback.assert_not_called()

    def test_nasa_rights_do_not_admit_third_party_or_other_provider(self):
        from pipeline.media_sources.video_search.alternatives import nasa_rights, NASA_EDITORIAL_LICENSE
        from pipeline.licenses import assess_license
        self.assertEqual(nasa_rights({'center':'JSC','title':'Apollo'}), NASA_EDITORIAL_LICENSE)
        for data in [{'center':'JPL'}, {'center':'JSC','description':'Copyright Getty'},
                     {'center':'JSC','secondary_creator':'Commercial studio'}, {}]:
            self.assertEqual(nasa_rights(data), 'unknown')
        self.assertTrue(assess_license('nasa', NASA_EDITORIAL_LICENSE)['requires_attribution'])
        self.assertFalse(assess_license('archive', NASA_EDITORIAL_LICENSE)['allowed'])

    def test_get_cache_and_retry_after_are_bounded(self):
        _hosts.clear()
        error = HTTPError('https://example.test/api', 429, 'rate limited', {'Retry-After':'2'}, None)
        fetch = Mock(side_effect=[error, b'{"value":1}'])
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'MEDIA_HTTP_CACHE_DIR':temporary}), patch('pipeline.media_http.time.sleep') as sleep:
            self.assertEqual(public_json('https://example.test/api', fetch), {'value':1})
            self.assertEqual(public_json('https://example.test/api', fetch), {'value':1})
            self.assertEqual(fetch.call_count, 2)
            sleep.assert_any_call(2.)
        _hosts.clear()

    def test_denied_catalogue_opens_circuit_and_does_not_retry(self):
        _hosts.clear()
        error = HTTPError('https://denied.test/api', 403, 'denied', {}, None)
        fetch = Mock(side_effect=error)
        with patch('pipeline.media_http.time.sleep'):
            with self.assertRaises(HTTPError):
                public_json('https://denied.test/api', fetch)
            with self.assertRaisesRegex(RuntimeError, 'circuit'):
                public_json('https://denied.test/another', fetch)
        self.assertEqual(fetch.call_count, 1)
        _hosts.clear()

    def test_review_cache_rejects_tampering(self):
        from pipeline.review_media_acquire import restore_cache
        from pipeline.media_pool import sha256, write_json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); cache = root/'cache'; bundle = cache/'bundle'
            bundle.mkdir(parents=True)
            Image.new('RGB', (320, 200)).save(bundle/'a.png')
            write_json(bundle/'manifest.json', [{'provider':'commons','license':'CC BY 4.0','file':'a.png','start_seconds':0}])
            write_json(cache/'cache.json', {'key':'key', 'files':{p.name:sha256(p) for p in bundle.iterdir()}})
            self.assertTrue(restore_cache(cache, root/'restored', 'key', 1))
            (bundle/'a.png').write_bytes(b'corrupt')
            self.assertFalse(restore_cache(cache, root/'bad', 'key', 1))

    def test_discovery_portal_is_not_an_additional_origin(self):
        origin = source_origin({'provider':'openverse','origin_provider':'commons'})
        self.assertEqual(origin['provider'], 'commons')
        self.assertEqual(origin['discovery_provider'], 'openverse')

    def test_review_only_tree_never_becomes_production_journey(self):
        from pipeline.run_journey import _discover_production_media
        from pipeline.media_pool import write_json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            episode = root/'scripts/2026-10-16'
            episode.mkdir(parents=True)
            media = root/'multimedia/2026-10-16'
            write_json(media/'manifest.json', [])
            write_json(media/'review_media_origin.json', {'kind':'review_only'})
            self.assertIsNone(_discover_production_media(episode))

    def test_fallback_acquisition_only_after_successful_but_invalid_plan(self):
        from pipeline.review_media_acquire import acquire_after_plan_failure
        from pipeline.media_pool import write_json
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'OPENAI_API_KEY':'test-not-a-key'}):
            root = Path(temporary); media = root/'media'
            write_json(media/'planning_trace.json', {'agent_trace':[{'status':'success'}]})
            self.assertTrue(acquire_after_plan_failure(root, media, 1))
            self.assertFalse(acquire_after_plan_failure(root, media, 124))
            write_json(media/'planning_trace.json', {'agent_trace':[{'status':'error','permanent_quota_error':True}]})
            self.assertFalse(acquire_after_plan_failure(root, media, 1))
            write_json(media/'planning_trace.json', {'agent_trace':[{'status':'success'}]})
            write_json(root/'media-pool/asset_pool.json', {})
            self.assertFalse(acquire_after_plan_failure(root, media, 1))

    def test_nasa_catalogue_ids_with_spaces_have_safe_local_identity(self):
        from pipeline.media_sources.video_search.alternatives import nasa_search, direct_media
        ident = 'Apollo 11 landing / camera 1'
        response = {'collection':{'items':[{'data':[{'nasa_id':ident,'center':'JSC','title':'Apollo landing'}]}]}}
        with patch('pipeline.media_sources.video_search.alternatives.api', return_value=response):
            rows = nasa_search('Apollo', 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['nasa_id'], ident)
        self.assertRegex(rows[0]['id'], r'^nasa-[a-f0-9]+$')
        self.assertIn('%2F', rows[0]['url'])
        with patch('pipeline.media_sources.video_search.alternatives.api', return_value={'collection':{'items':[{'href':'https://images-assets.nasa.gov/a.mp4'}]}}) as api:
            direct_media(rows[0])
        self.assertTrue(api.call_args.args[0].endswith('Apollo%2011%20landing%20%2F%20camera%201'))

    def test_model_bundle_persists_measured_timeline_reach(self):
        import asyncio
        from unittest.mock import AsyncMock
        from pipeline import review_media as media
        from pipeline.media_pool import write_json
        cue = {'slot_number':1,'start_seconds':90,'end_seconds':100,'mode':'media','visual_query':'laboratory','visual_role':'context'}
        record = {'shot_number':1,'file':'a.jpg','provider':'commons','license':'CC BY 4.0','asset_type':'image'}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'MEDIA_RETRIEVAL_MODE':'off'}):
            root = Path(temporary); episode = root/'scripts'; episode.mkdir()
            (episode/'script.txt').write_text('science '*200)
            write_json(episode/'episode_plan.json', {'beats':[{'beat_id':'b1'}]})
            write_json(episode/'script_sections.json', {'sections':[{'section_key':'beat:b1','word_count':200}]})
            with patch.object(media, 'run_agent', new=AsyncMock(return_value={'multimedia_plan':{'segments':[cue]}})), patch.object(media, 'timeline_duration_seconds', return_value=100), patch.object(media, 'normalize_multimedia_plan', return_value=([cue],[])), patch.object(media, 'enforce_opening_dense_media', side_effect=lambda p,*a,**k:p), patch.object(media, 'enforce_synthesis_media', side_effect=lambda p,*a:p), patch.object(media, 'download_shot_asset', return_value=record), patch.object(media, 'deduplicate_materialized_media', side_effect=lambda m,s,**k:(m,s,[])), patch.object(media, 'write_edit_manifest'), patch.object(media, 'write_credits'), patch.object(media, 'create_zip'):
                asyncio.run(media.build_review_media(episode_dir=episode, output_dir=root/'media', max_media_downloads=1, zip_path=root/'media.zip'))
            plan = json.loads((root/'media/plan.json').read_text())
            self.assertEqual(plan['coverage_ratio'], 1.)
