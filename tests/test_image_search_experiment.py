import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from experiments.image_search import model, sources, run


def plan(kind="person"):
    return model.Plan(subject="Albert Einstein" if kind == "person" else "Ancient Rome", kind=kind,
                      unambiguous=True, interpretation="test", queries=["Albert Einstein"], museum_query="Roman",
                      date_start=-753 if kind == "historical" else None,
                      date_end=476 if kind == "historical" else None,
                      allowed_types=["person_photo"] if kind == "person" else ["object_photo", "site_photo"])


def item(title="Albert Einstein, portrait"):
    return sources.candidate("commons", 1, "https://commons.wikimedia.org/wiki/File:Example.jpg",
                             "https://upload.wikimedia.org/example.jpg",
                             {"title": title, "description": "A catalogue photograph", "license": "Public domain"})


def decision(quote="Albert Einstein, portrait", field="title", depiction="person_photo"):
    return dict(key="c001", relevance="direct", evidence_field=field, evidence_quote=quote,
                depiction=depiction, reason="Atribución explícita del catálogo.")


class ImageSearchTests(unittest.TestCase):
    def test_person_exact_name_and_literal_quote_are_required(self):
        self.assertIsNone(run.metadata_gate(plan(), item(), decision()))
        for wrong in ("Elsa Einstein, portrait", "Einstein Cross", "Anonymous scientist"):
            self.assertIsNotNone(run.metadata_gate(plan(), item(wrong), decision(wrong)))
        self.assertIsNotNone(run.metadata_gate(plan(), item(), decision("Invented caption")))

    def test_indirect_name_and_creator_are_not_depiction_evidence(self):
        row = item("A monument named after Albert Einstein")
        self.assertIsNotNone(run.metadata_gate(plan(), row, decision(row['metadata']['title'])))
        row = item("Notebook")
        row['metadata']['creator'] = 'Albert Einstein'
        self.assertIsNotNone(run.metadata_gate(plan(), row, decision('Albert Einstein', 'creator')))

    def test_statue_cannot_replace_a_person_photograph(self):
        d = decision(depiction="object_photo")
        self.assertIsNotNone(run.metadata_gate(plan(), item(), d))
        visual = dict(kind="object_photo", usable=True, obvious_synthetic_or_meme=False)
        self.assertIsNotNone(run.visual_gate(plan(), decision(), visual))

    def test_historical_object_date_is_distinct_from_photo_date(self):
        p = plan("historical")
        row = item("Roman portrait bust")
        row.update(object_start=100, object_end=200)
        row['metadata']['date'] = 'Photographed in 2025'
        d = decision('Roman portrait bust', depiction='object_photo')
        self.assertIsNone(run.metadata_gate(p, row, d))
        row.update(object_start=1750, object_end=1800)
        self.assertIsNotNone(run.metadata_gate(p, row, d))

    def test_uncertainty_and_generated_metadata_fail_closed(self):
        d = decision();d['relevance'] = 'uncertain'
        self.assertIsNotNone(run.metadata_gate(plan(), item(), d))
        row = item();row['metadata']['description'] = 'AI-generated portrait using Midjourney'
        self.assertIsNotNone(run.metadata_gate(plan(), row, decision()))

    def test_image_hosts_and_redirects_are_restricted(self):
        for url in ('http://upload.wikimedia.org/a.jpg', 'https://upload.wikimedia.org.evil.test/a',
                    'https://127.0.0.1/a', 'https://user:pass@upload.wikimedia.org/a',
                    'https://upload.wikimedia.org:123/a'):
            with self.assertRaises(ValueError):
                sources.validate_url(url, sources.MEDIA_HOSTS['commons'])
        with self.assertRaises(ValueError):
            sources.Redirect(sources.MEDIA_HOSTS['commons']).redirect_request(None, None, 302, '', {}, 'https://evil.test/a')

    def test_catalogue_id_and_page_url_cannot_inject_paths_or_links(self):
        with self.assertRaises(ValueError):
            sources.candidate('commons', '../escape', 'https://commons.wikimedia.org/a',
                              'https://upload.wikimedia.org/a', {})
        with self.assertRaises(ValueError):
            sources.candidate('commons', '1', 'javascript:alert(1)', 'https://upload.wikimedia.org/a', {})

    def test_actual_image_decode_size_and_duplicate_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'image.jpg'
            Image.new('RGB', (800, 600), 'blue').save(p)
            media = run.inspect_file(p)
            self.assertEqual(media['width'], 800)
            self.assertTrue(run.is_duplicate(media, [media]))
            p.write_bytes(b'<html>This is not a JPEG</html>')
            with self.assertRaises(Exception):
                run.inspect_file(p)
            Image.new('RGB', (120, 80)).save(p)
            with self.assertRaisesRegex(ValueError, 'resolution'):
                run.inspect_file(p)

    def test_provider_failure_does_not_stop_other_catalogues(self):
        with patch.dict(sources.PROVIDERS, {'commons': lambda *a: (_ for _ in ()).throw(sources.Blocked('403')),
                                            'loc': lambda *a: [item()]}):
            rows, log = sources.discover(plan(), ['commons', 'loc'], {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(log[0]['status'], 'blocked')

    def test_catalogue_variants_are_deduplicated_despite_crop_hash_changes(self):
        original = item('File:Albert Einstein Head.jpg')
        restored = item('File:Albert Einstein Head cleaned.jpg')
        cropped = item('File:Albert Einstein Head (cropped).jpg')
        self.assertEqual(run.catalogue_family(original), run.catalogue_family(restored))
        self.assertEqual(run.catalogue_family(original), run.catalogue_family(cropped))
        a = dict(sha256='a', pixel_sha256='a', dhash='0000000000000000', catalogue_family=run.catalogue_family(original))
        b = dict(sha256='b', pixel_sha256='b', dhash='ffffffffffffffff', catalogue_family=run.catalogue_family(restored))
        self.assertTrue(run.is_duplicate(a, [b]))
        self.assertNotEqual(run.catalogue_family(original), run.catalogue_family(item('File:Albert Einstein 1916.jpg')))

    def test_met_uses_paginated_api_and_actual_public_domain_flag(self):
        seen = []
        def request(url, **kwargs):
            seen.append(url)
            if '/search?' in url:
                return {'objectIDs': [9, 1, 2]}
            if url.endswith('/9'):
                raise RuntimeError('Provider HTTP 404')
            return {'isPublicDomain': url.endswith('/1'), 'primaryImage': 'https://images.metmuseum.org/a.jpg',
                    'objectURL': 'https://www.metmuseum.org/art/collection/search/1', 'title': 'Roman bust',
                    'objectBeginDate': 100, 'objectEndDate': 200}
        with patch.object(sources, 'request_json', side_effect=request):
            rows = sources.met(plan('historical'), {})
        self.assertEqual(len(rows), 1)
        self.assertIn('/v1.1/search?', seen[0])

    def test_entity_resolution_disambiguates_person_from_train_and_painting(self):
        def lookup(base, **params):
            if params['action'] == 'wbsearchentities':
                return {'search': [{'id': 'Q1', 'label': 'Albert Einstein'},
                                   {'id': 'Q2', 'label': 'Albert Einstein'}]}
            def entity(kind):
                return {'claims': {'P31': [{'mainsnak': {'datavalue': {'value': {'id': kind}}}}]}}
            return {'entities': {'Q1': entity('Q5'), 'Q2': entity('Q870')}}
        with patch.object(sources, 'api', side_effect=lookup):
            result = sources.resolve_entity(plan())
        self.assertEqual(result['id'], 'Q1')

    def test_model_cannot_invent_or_duplicate_candidate_references(self):
        for key in ('c999', 'c001'):
            decisions = [dict(decision(), key=key)]
            if key == 'c001':decisions *= 2
            with patch.object(model, 'respond', return_value=(json.dumps({'items': decisions}), {})):
                with self.assertRaisesRegex(ValueError, 'Unknown or duplicated'):
                    model.assess(plan(), [item()], {}, None)

    def test_ambiguous_plan_stops_before_search(self):
        d = plan().model_dump();d['unambiguous'] = False
        with patch.object(model, 'respond', return_value=(json.dumps(d), {})):
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                model.make_plan('Jordan', None)

    def test_partial_count_is_failure_and_gallery_escapes_untrusted_text(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            m = {'description': '<script>alert(1)</script>', 'count': 5, 'sources': ['commons'], 'items': []}
            self.assertFalse(run.report(p, m))
            self.assertNotIn('<script>', (p/'gallery.html').read_text())
            self.assertEqual(m['summary']['downloaded'], 0)

    def test_failed_visual_leaves_no_image_in_artifact(self):
        p = plan()
        args = argparse.Namespace(description='Einstein', count=1, sources='commons')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);output = root/'out';output.mkdir()
            fixture = root/'fixture.jpg';Image.new('RGB', (800, 600), 'blue').save(fixture)
            with patch.object(model, 'make_plan', return_value=(p, {})), patch.object(sources, 'resolve_entity', return_value={}):
                with patch.object(sources, 'discover', return_value=([item()], [])), patch.object(model, 'assess', return_value=({'commons:1': decision()}, {})):
                    with patch.object(sources, 'fetch', return_value=fixture.read_bytes()), patch.object(model, 'inspect_visual', side_effect=RuntimeError('unavailable')):
                        self.assertFalse(run.execute(args, output))
            self.assertFalse(list(output.rglob('*.jpg')))
            self.assertFalse(list(root.glob('image-candidate-*')))


if __name__ == '__main__':
    unittest.main()
