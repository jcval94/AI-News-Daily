import unittest
from experiments.media_stress.run import audit, evidence_matches
from experiments.video_search.providers import duration_seconds
from experiments.video_search.run import next_candidate

class MediaStressTests(unittest.TestCase):
    def test_query_and_model_reason_cannot_prove_match(self):
        case={'evidence_groups':[['khan baba']]}
        self.assertFalse(evidence_matches(case,{'queries':['Khan Baba'],'assessment':{'reason':'Khan Baba'},'title':'Baba Khan'}))
        self.assertTrue(evidence_matches(case,{'metadata':{'title':'Khan Baba in Pakistan'}}))

    def test_event_requires_all_groups(self):
        case={'evidence_groups':[['toyota war'],['1987','chad']]}
        self.assertFalse(evidence_matches(case,{'title':'Toyota Hilux in Chad 1987'}))
        self.assertTrue(evidence_matches(case,{'title':'Toyota War in Chad'}))

    def test_download_is_not_automatically_exact(self):
        result=audit({'id':'x','label':'x','description':'x','evidence_groups':[['x']]},'videos',{'items':[]},[{'title':'x'}])
        self.assertEqual(result['textual_candidate_matches'],1)
        self.assertEqual(result['downloaded'],0)
        self.assertIsNone(result['exact_success'])

    def test_person_cannot_be_replaced_by_associated_event(self):
        from experiments.video_search.plan import IdentityConstraint, identity_matches
        from types import SimpleNamespace
        plan = SimpleNamespace(required_identity=IdentityConstraint(mention='Tsutomu Yamaguchi', aliases=['Yamaguchi Tsutomu']))
        self.assertFalse(identity_matches(plan, {'title':'Hiroshima and Nagasaki, Japan', 'description':'Produced in 1946'}))
        self.assertTrue(identity_matches(plan, {'title':'Tsutomu Yamaguchi: surviving both bombings'}))

    def test_off_never_fetches_captions_or_calls_asr(self):
        from unittest.mock import patch
        from experiments.video_search import enrichment
        from experiments.video_search.run import download
        import inspect
        self.assertEqual(inspect.signature(download).parameters['transcript_mode'].default, 'off')
        with patch.object(enrichment, 'fetch_caption') as captions, patch.object(enrichment, 'transcribe_audio') as asr:
            result = enrichment.transcript(None, None, {'subtitles': {}}, {'audio_codec': 'aac'}, 'full', 'off', None)
        self.assertEqual(result['status'], 'disabled')
        captions.assert_not_called()
        asr.assert_not_called()

    def test_duration_formats_and_preference(self):
        for value in ('00:02:10','PT2M10S','130',130):
            self.assertEqual(duration_seconds(value),130)
        for value in ('unknown',0,'NaN','inf'):
            self.assertIsNone(duration_seconds(value))
        rows=[dict(key=str(i),relevant=True,source='archive',creator='x',events=[],duration_seconds=d)
              for i,d in enumerate([900,None,180,30])]
        self.assertEqual(next_candidate(rows,set(),[],[],{})['duration_seconds'],30)
        rows[0]['events']=['required']
        from types import SimpleNamespace
        self.assertEqual(next_candidate(rows,set(),[],[SimpleNamespace(mention='required')],{})['duration_seconds'],900)
