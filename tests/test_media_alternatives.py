import unittest
from types import SimpleNamespace
from unittest.mock import patch

from experiments import public_media
from experiments.image_search import alternatives as images, sources, run
from experiments.video_search import alternatives as videos


class AlternativeMediaTests(unittest.TestCase):
    def test_federated_host_rejects_private_mixed_dns(self):
        rows = [(2, 1, 6, '', ('8.8.8.8', 443)), (2, 1, 6, '', ('127.0.0.1', 443))]
        with patch.object(public_media.socket, 'getaddrinfo', return_value=rows):
            with self.assertRaises(ValueError):
                public_media.public_addresses('federated.example')
        for url in ('http://example.com/a', 'https://u:p@example.com/a', 'https://example.com:22/a'):
            with self.assertRaises(ValueError):
                public_media.validate_url(url)

    def test_peertube_private_live_and_nsfw_are_excluded(self):
        base = dict(uuid='a' * 8 + '-aaaa-aaaa-aaaa-' + 'a' * 12, url='https://tube.example/videos/watch/a',
                    name='Exact subject', privacy={'id': 1}, isLive=False, nsfw=False)
        with patch.object(videos, 'api', return_value={'data': [base, dict(base, privacy={'id': 2}),
                                                            dict(base, isLive=True), dict(base, nsfw=True)]}) as api:
            rows = videos.peertube_search('Exact subject', 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(api.call_args.kwargs['search'], '"Exact subject"')

    def test_peertube_owner_disabled_download_is_respected(self):
        item = dict(source='peertube', id='abc', url='https://tube.example/videos/watch/abc', title='Subject', creator='A', license='unknown')
        base = dict(uuid='abc', privacy={'id': 1}, isLive=False, downloadEnabled=False,
                    files=[dict(fileUrl='https://tube.example/movie.mp4', size=20, resolution={'id': 360})])
        with patch.object(videos, 'api', return_value=base):
            with self.assertRaisesRegex(ValueError, 'not enabled'):
                videos.direct_media(item)
        with patch.object(videos, 'api', return_value=dict(base, downloadEnabled=True, files=[], streamingPlaylists=[{'playlistUrl': 'https://tube.example/a.m3u8'}])):
            with self.assertRaisesRegex(ValueError, 'HLS/P2P'):
                videos.direct_media(item)

    def test_nasa_prefers_small_derivative(self):
        item = dict(source='nasa', id='abc', title='Subject', creator='NASA', license='consult source')
        with patch.object(videos, 'api', return_value={'collection': {'items': [
                {'href': 'https://images-assets.nasa.gov/abc~orig.mp4'},
                {'href': 'https://images-assets.nasa.gov/abc~small.mp4'}]}}):
            url, _, hosts = videos.direct_media(item)
        self.assertTrue(url.endswith('~small.mp4'))
        with self.assertRaises(ValueError):
            public_media.validate_url('https://unrelated.example/a.mp4', hosts)

    def test_article_association_does_not_invent_depiction_evidence(self):
        plan = SimpleNamespace(subject='Albert Einstein', queries=['Albert Einstein'], kind='person',
                               allowed_types=['person_photo'], date_start=None)
        page = {'query': {'pages': [dict(title='Albert Einstein', pageimage='Anonymous.jpg')]}}
        info = {'query': {'pages': [dict(title='File:Anonymous.jpg', imageinfo=[dict(
            url='https://upload.wikimedia.org/a.jpg', descriptionurl='https://commons.wikimedia.org/wiki/File:Anonymous.jpg',
            mime='image/jpeg', extmetadata={'ImageDescription': {'value': 'Anonymous portrait'}})])]}}
        with patch.object(images, 'api', side_effect=[page, info, page, info]):
            found = images.wikipedia(plan, {'status': 'unresolved'})
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0]['entity_anchor'])
        self.assertEqual(found[0]['metadata']['description'], 'Anonymous portrait')
        decision = dict(relevance='direct', evidence_field='description', evidence_quote='Anonymous portrait', depiction='person_photo')
        self.assertIsNotNone(run.metadata_gate(plan, found[0], decision))

    def test_openverse_unknown_download_host_is_not_fetched(self):
        plan = SimpleNamespace(subject='Einstein')
        data = {'results': [dict(id='a'*8+'-aaaa-aaaa-aaaa-'+'a'*12, title='Einstein', url='https://untrusted.example/a.jpg')]}
        with patch.object(images, 'api', return_value=data):
            self.assertEqual(images.openverse(plan, {}), [])

    def test_discovery_reserves_capacity_for_new_sources(self):
        def many(source):
            return [dict(key=f'{source}:{i}', source=source) for i in range(80)]
        with patch.dict(sources.PROVIDERS, {'old': lambda p,e: many('old')}), \
             patch.dict(images.PROVIDERS, {'new': lambda p,e: many('new')}):
            rows, diagnostics = sources.discover(None, ['old', 'new'], {})
        self.assertEqual(len(rows), 80)
        self.assertEqual(sum(x['source'] == 'new' for x in rows), 40)
        self.assertTrue(all(d['status'] == 'ok' for d in diagnostics))


if __name__ == '__main__':
    unittest.main()
