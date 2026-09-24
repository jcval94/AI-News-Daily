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
