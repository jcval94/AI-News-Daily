import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.video_search import enrichment as e


class VideoEnrichmentTests(unittest.TestCase):
    def test_vtt_preserves_timestamps_and_removes_rolling_duplicate(self):
        text = 'WEBVTT\n\n00:00.000 --> 00:02.000\n<c>Enron cayó</c>\n\n00:01.000 --> 00:03.000\nEnron cayó en 2001\n'
        segments = e.parse_captions(text, 'vtt')
        self.assertEqual(segments[1]['start'], 1)
        self.assertEqual(e.plain_transcript(segments), 'Enron cayó en 2001')

    def test_json3_and_srt_are_normalized(self):
        raw = json.dumps({'events': [{'tStartMs': 1000, 'dDurationMs': 2000,
                                     'segs': [{'utf8': 'Enron &amp; fraude'}]}]})
        self.assertEqual(e.parse_captions(raw, 'json3')[0],
                         {'start': 1, 'end': 3, 'text': 'Enron & fraude'})
        self.assertEqual(e.parse_captions('1\n00:00:01,000 --> 00:00:02,000\nHola\n', 'srt')[0]['end'], 2)

    def test_captions_prefer_publisher_and_spanish(self):
        raw = {'subtitles': {'en': [{'url': 'https://www.youtube.com/en', 'ext': 'vtt'}],
                             'es': [{'url': 'https://www.youtube.com/es', 'ext': 'json3'}]},
               'automatic_captions': {'es': [{'url': 'https://www.youtube.com/auto', 'ext': 'vtt'}]}}
        first = next(e.caption_options(raw))
        self.assertEqual((first['language'], first['method']), ('es', 'publisher_captions'))

    def test_no_heatmap_is_not_a_fabricated_flat_graph(self):
        result = e.replay_data({}, 'youtube')
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['bins'], [])
        self.assertEqual(e.replay_data({}, 'archive')['status'], 'not_applicable')

    def test_heatmap_validates_values_and_preserves_real_peak(self):
        rows = [{'start_time': 0, 'end_time': 10, 'value': .2},
                {'start_time': 10, 'end_time': 20, 'value': 1.0}]
        result = e.replay_data({'heatmap': rows}, 'youtube')
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['peaks'][0]['start_time'], 10)
        rows[1]['value'] = float('nan')
        self.assertEqual(e.replay_data({'heatmap': rows}, 'youtube')['status'], 'invalid')

    def test_caption_host_and_scheme_are_restricted(self):
        e.allowed_caption_url('https://www.youtube.com/api/timedtext?v=test')
        e.allowed_caption_url('https://ia800001.us.archive.org/example.vtt')
        for url in ('http://youtube.com/a', 'https://127.0.0.1/a', 'https://youtube.com.evil.test/a'):
            with self.assertRaises(ValueError):
                e.allowed_caption_url(url)

    def test_generated_transcript_is_labelled_and_audio_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            media = {'audio_codec': 'aac', 'duration_seconds': 15}
            with patch.object(e, 'transcribe_audio', return_value=([{'start': 1, 'end': 2, 'text': 'Hola'}], 'es')):
                result = e.enrich(path/'source.mp4', path, {}, media, 'archive', 'clip', 'auto', None)
            self.assertEqual(result['transcript']['method'], 'generated_asr')
            self.assertEqual(result['transcript']['scope'], 'downloaded_clip')
            self.assertEqual((path/'transcript.txt').read_text(), 'Hola\n')
            self.assertFalse((path/'most_replayed.svg').exists())
            with patch.object(e, 'transcribe_audio', side_effect=RuntimeError('quota')):
                failed = e.transcript(path/'source.mp4', path, {}, media, 'full', 'auto', None)
            self.assertEqual(failed['status'], 'failed')

    @unittest.skipUnless(importlib.util.find_spec('matplotlib'), 'optional graph renderer')
    def test_available_replay_renders_standalone_svg(self):
        data = e.replay_data({'heatmap': [{'start_time': 0, 'end_time': 10, 'value': .3},
                                        {'start_time': 10, 'end_time': 20, 'value': 1}]}, 'youtube')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'replay.svg'
            e.plot_replay(data, path)
            self.assertIn('<svg', path.read_text())


if __name__ == '__main__':
    unittest.main()
