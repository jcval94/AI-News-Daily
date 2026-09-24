import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from experiments.image_search.run import inspect_file
from experiments.media_pack.run import Pack, asset_name, quality_tier


class MediaPackTests(unittest.TestCase):
    def test_low_resolution_is_opt_in_not_a_benchmark_relaxation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'small.jpg'
            Image.new('RGB', (408, 244), 'blue').save(path)
            with self.assertRaisesRegex(ValueError, 'minimum'):
                inspect_file(path)
            media = inspect_file(path, min_short=80, min_long=160)
            self.assertEqual(quality_tier(media, 'image'), 'lowres')
            Image.new('RGB', (79, 160)).save(path)
            with self.assertRaises(ValueError):
                inspect_file(path, min_short=80, min_long=160)

    def test_names_are_safe_deterministic_and_collision_resistant(self):
        row = {'key': 'commons:1', 'id': '1', 'source': '../../evil', 'sha256': 'f'*64,
               'metadata': {'title': '../../Título / ' + 'a'*100}}
        name = asset_name('../Tema', row, 'context', 'lowres', '.jpg')
        self.assertNotIn('/', name)
        self.assertNotIn('..', name)
        self.assertLess(len(name), 200)
        self.assertEqual(name, asset_name('../Tema', row, 'context', 'lowres', '.jpg'))
        self.assertNotEqual(name, asset_name('../Tema', {**row, 'key': 'commons:2'}, 'context', 'lowres', '.jpg'))
        with self.assertRaises(ValueError):
            asset_name('Tema', row, 'exact', 'standard', '../../x')

    def test_manifest_preserves_context_lowres_hash_and_rights(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'out'
            output.mkdir()
            path = Path(tmp) / 'small.jpg'
            Image.new('RGB', (408, 244), 'red').save(path)
            pack = Pack(output, 'Subject', 2, 0)
            row = {'key': 'commons:1', 'id': '1', 'source': 'commons', 'url': 'https://commons.wikimedia.org/wiki/File:1',
                   'metadata': {'title': 'A place', 'license': 'CC-BY-SA'},
                   'media': inspect_file(path, min_short=80, min_long=160)}
            need = {'subject': 'Place', 'suggested_use': 'Context only', 'limitation': 'Not the person'}
            pack.publish(path, row, need, 'context', 'image')
            data = json.loads((output / 'manifest.json').read_text())
            asset = data['assets'][0]
            self.assertEqual(asset['relation'], 'context')
            self.assertEqual(asset['quality'], 'lowres')
            self.assertFalse(asset['license_validated'])
            self.assertFalse(data['production_ready'])
            self.assertEqual(data['summary']['shortfall_images'], 1)
            self.assertEqual(data['summary']['exact'], 0)
            self.assertEqual(hashlib.sha256((output / asset['path']).read_bytes()).hexdigest(), asset['sha256'])
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                pack.publish(path, {**row, 'key': 'other:2', 'url': 'https://example.org'}, need, 'exact', 'image')
            with patch('experiments.media_pack.run.MAX_PACK_BYTES', 1):
                self.assertFalse(pack.room())

    def test_no_context_option_never_calls_context_planner(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Pack(Path(tmp), 'Rare person', 3, 0, allow_context=False)
            with patch.object(pack, 'image_search'), patch('experiments.media_pack.run.context_plan') as context:
                pack.execute()
            context.assert_not_called()
            self.assertEqual(pack.manifest['summary']['status'], 'empty')
            self.assertTrue((Path(tmp) / 'SHA256SUMS').exists())


if __name__ == '__main__':
    unittest.main()
