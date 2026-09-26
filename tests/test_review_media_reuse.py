import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from pipeline.review_media_reuse import reuse_media
from pipeline.run_journey import _discover_production_media


class ReviewMediaReuseTests(unittest.TestCase):
    def fixture(self, root):
        episode = root/'scripts/2026-09-04'; episode.mkdir(parents=True)
        (episode/'run_state.json').write_text('{"status":"approved"}')
        media = root/'multimedia/2026-09-04'; media.mkdir(parents=True)
        manifest = []
        for i, color in enumerate(('red', 'blue')):
            Image.new('RGB', (400, 240), color).save(media/f'{i}.png')
            manifest.append({'file':f'{i}.png', 'license_valid':True, 'start_seconds':i*5})
        (media/'manifest.json').write_text(json.dumps(manifest))
        (media/'media_pool_summary.json').write_text('{"mode":"integrated"}')
        return episode, media, manifest

    def test_reuse_preserves_pool_and_labels_staging_without_production_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); episode,media,_=self.fixture(root)
            (root/'integration-result.json').write_text('{"success":true,"promoted":false}')
            output=root/'review/2026-09-04'; archive=root/'review.zip'
            self.assertTrue(reuse_media(episode,output,archive,minimum=2,opening_minimum=2))
            self.assertTrue(archive.is_file())
            self.assertEqual((output/'media_pool_summary.json').read_bytes(),(media/'media_pool_summary.json').read_bytes())
            self.assertEqual(json.loads((output/'review_media_origin.json').read_text())['kind'],'reused_staging')
            self.assertIsNone(_discover_production_media(episode))

    def test_invalid_bundle_never_creates_reuse_destination(self):
        for problem in ('duplicate', 'missing', 'license', 'readiness', 'failed_staging', 'traversal'):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); episode,media,manifest=self.fixture(root)
                if problem=='duplicate': (media/'1.png').write_bytes((media/'0.png').read_bytes())
                if problem=='missing': (media/'1.png').unlink()
                if problem=='license': manifest[0]['license_valid']=False
                if problem=='readiness': (episode/'asset_readiness.json').write_text('{"gate":{"ready_to_record":false}}')
                if problem=='failed_staging': (root/'integration-result.json').write_text('{"success":false}')
                if problem=='traversal': manifest[0]['file']='../../outside.png'
                (media/'manifest.json').write_text(json.dumps(manifest))
                self.assertFalse(reuse_media(episode,root/'review',root/'review.zip',minimum=2,opening_minimum=2))
                self.assertFalse((root/'review').exists())
