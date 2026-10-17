from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.media_origin import label_manifest, source_origin
from pipeline.pages_history import _patch_episode_site
from pipeline.review_media_sources import upgrade_media_sources


def page(files):
    return '<html><head></head><body><section id="multimedia" data-search-group><h2>Medios</h2>' + ''.join(
        f'<article class="media-card searchable-card"><img src="media/{file}"><div class="media-meta">Item</div></article>' for file in files
    ) + '</section></body></html>'


class MediaSourceObservabilityTests(unittest.TestCase):
    def test_provider_aliases_and_external_local_unknown(self):
        origins = [source_origin({'provider': provider}) for provider in ['commons', 'wikimedia', 'wikimedia_commons']]
        self.assertEqual(len({o['provider'] for o in origins}), 1)
        self.assertTrue(all(o['kind'] == 'external' for o in origins))
        self.assertEqual(source_origin({'provider': 'generated_fallback'})['kind'], 'local')
        self.assertEqual(source_origin({'provider': 'new-unverified-provider'})['kind'], 'unknown')
        self.assertEqual(source_origin({})['provider'], 'unknown')

    def test_url_inference_is_bounded_and_does_not_override_provider(self):
        self.assertEqual(source_origin({'source_url': 'https://www.pexels.com/photo/1'})['basis'], 'source_url')
        self.assertEqual(source_origin({'source_url': 'https://pexels.com.evil.test/photo/1'})['kind'], 'unknown')
        self.assertEqual(source_origin({'provider': 'generated_fallback', 'source_url': 'https://pexels.com/photo/1'})['kind'], 'local')

    def test_internal_labels_preserve_raw_metadata_and_do_not_trust_stale_labels(self):
        raw = {'provider': 'wikimedia_commons', 'file': 'a.jpg', 'source_origin': {'provider': 'pexels'}}
        labeled = label_manifest([raw])[0]
        self.assertEqual(labeled['provider'], 'wikimedia_commons')
        self.assertEqual(labeled['source_origin']['provider'], 'commons')
        self.assertEqual(raw['source_origin']['provider'], 'pexels')
        self.assertEqual(label_manifest([labeled]), [labeled])
        pool = source_origin({'provider': 'commons', 'media_provenance': {'source_asset_id': 'documented-id'}})
        self.assertEqual(pool['acquisition'], 'documentary_pool')

    def test_html_matches_by_filename_not_order_and_escapes_labels(self):
        manifest = [{'file': 'b.jpg', 'provider': 'generated_fallback'}, {'file': 'a.jpg', 'provider': 'pexels'}]
        result = upgrade_media_sources(page(['a.jpg', 'b.jpg']), manifest)
        cards = result.split('<article')[1:]
        self.assertIn('data-origin-provider="pexels"', cards[0])
        self.assertIn('data-origin-provider="generated_fallback"', cards[1])
        self.assertIn('Pexels · 1', result)
        self.assertIn('Local · 1', result)
        self.assertEqual(upgrade_media_sources(result, manifest), result)
        malicious = upgrade_media_sources(page(['a.jpg']), [{'file': 'a.jpg', 'provider': '<script>bad</script>'}])
        self.assertNotIn('<script>bad</script>', malicious)

    def test_missing_matching_metadata_is_not_guessed_from_position(self):
        result = upgrade_media_sources(page(['other.jpg']), [{'file': 'a.jpg', 'provider': 'pexels'}])
        self.assertIn('data-origin-provider="unknown"', result)
        self.assertNotIn('data-origin-provider="pexels"', result)

    def test_history_upgrade_preserves_media_and_backfills_downloadable_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'artifacts').mkdir()
            (root / 'index.html').write_text(page(['a.jpg']))
            path = root / 'artifacts/media-manifest.json'
            path.write_text(json.dumps([{'file': 'a.jpg', 'provider': 'pexels'}]))
            _patch_episode_site(root)
            self.assertIn('id="media-origin-filters"', (root / 'index.html').read_text())
            self.assertEqual(json.loads(path.read_text())[0]['source_origin']['kind'], 'external')
            first = (root / 'index.html').read_text()
            _patch_episode_site(root)
            self.assertEqual((root / 'index.html').read_text(), first)

    def test_absent_or_invalid_historical_manifest_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text(page(['a.jpg']))
            _patch_episode_site(root)
            self.assertNotIn('id="media-origin-filters"', (root / 'index.html').read_text())
