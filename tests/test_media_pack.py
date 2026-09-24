import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import ExitStack

from PIL import Image

from experiments.image_search.run import inspect_file
from experiments.media_pack.run import Pack, asset_name, quality_tier, literal_decision
from tests.test_image_search_experiment import plan, item, decision


class MediaPackTests(unittest.TestCase):
    def test_quote_wrapper_repair_still_requires_verbatim_source_evidence(self):
        row = item()
        for quote in ['"Albert Einstein"', '“Albert Einstein”', '«Albert Einstein»']:
            self.assertEqual(literal_decision(row, decision(quote))['evidence_quote'], 'Albert Einstein')
        for quote in ['"Elsa Einstein"', '"albert einstein"', '"Albert  Einstein"']:
            self.assertEqual(literal_decision(row, decision(quote))['evidence_quote'], quote)

    def test_standard_first_and_exact_lowres_before_context(self):
        rows = [item(), {**item(), 'key': 'commons:2', 'id': '2',
                        'url': 'https://commons.wikimedia.org/wiki/File:2.jpg',
                        'metadata': {**item()['metadata'], 'title': 'Albert Einstein outdoors'}}]
        data = []
        for dims, direction in [((408, 244), 1), ((800, 600), -1)]:
            im = Image.new('RGB', dims)
            im.putdata([(int(255*x/(dims[0]-1)) if direction == 1 else int(255*(1-x/(dims[0]-1))), 0, 0)
                        for y in range(dims[1]) for x in range(dims[0])])
            buffer = io.BytesIO()
            im.save(buffer, format='JPEG')
            data.append(buffer.getvalue())
        for quota, expected in [(1, ['standard']), (2, ['standard', 'lowres'])]:
            with self.subTest(quota=quota), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                pack = Pack(Path(tmp), 'Albert Einstein', quota, 0)
                stack.enter_context(patch('experiments.media_pack.run.model.make_plan', return_value=(plan(), {})))
                stack.enter_context(patch('experiments.media_pack.run.sources.resolve_entity', return_value={}))
                stack.enter_context(patch('experiments.media_pack.run.sources.discover', return_value=(rows, [])))
                stack.enter_context(patch('experiments.media_pack.run.model.assess', return_value=({r['key']: decision('Albert Einstein') for r in rows}, {})))
                stack.enter_context(patch('experiments.media_pack.run.sources.fetch', side_effect=data))
                stack.enter_context(patch('experiments.media_pack.run.model.inspect_visual', return_value=(
                    {'kind': 'person_photo', 'usable': True, 'obvious_synthetic_or_meme': False}, {})))
                need = {'description': 'Albert Einstein', 'subject': 'Albert Einstein', 'suggested_use': 'Portrait', 'limitation': 'Review'}
                pack.image_search(need, 'exact', quota)
                self.assertEqual([a['quality'] for a in pack.manifest['assets']], expected)
                self.assertTrue(all(a['relation'] == 'exact' for a in pack.manifest['assets']))

    def test_replay_graph_and_json_are_preserved_as_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            output = Path(tmp) / 'out'
            output.mkdir()
            path = source / 'source.mp4'
            path.write_bytes(b'already verified video fixture')
            (source / 'most_replayed.svg').write_text('<svg></svg>')
            (source / 'most_replayed.json').write_text('{"status":"available"}')
            pack = Pack(output, 'Subject', 1, 1)
            pack.publish(path, {'key': 'youtube:x', 'id': 'x', 'source': 'youtube',
                'url': 'https://youtube.com/watch?v=x', 'media': {'width': 640, 'height': 360}},
                {'subject': 'Subject', 'suggested_use': 'Review', 'limitation': 'Proxy'}, 'exact', 'video')
            asset = pack.manifest['assets'][0]
            for name in ['most_replayed.svg', 'most_replayed.json']:
                self.assertEqual((output / asset['sidecar_paths'][name]).read_bytes(), (source / name).read_bytes())

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
