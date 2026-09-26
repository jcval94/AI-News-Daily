import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.media_cost_audit import cost_audit


class MediaCostAuditTests(unittest.TestCase):
    def test_cached_tokens_are_not_billed_twice_and_unknown_is_not_free(self):
        result = cost_audit({'model_calls': 2, 'model_usage': [
            {'model': 'gpt-5.4-nano-2026-03-17', 'usage': {'input_tokens': 1000,
             'input_tokens_details': {'cached_tokens': 400}, 'output_tokens': 200}},
            {'model': 'gpt-5.4-nano', 'status': 'error', 'usage': None}]})
        self.assertAlmostEqual(result['estimated_known_usd'], 0.000378)
        self.assertEqual(result['unpriced_attempts'], 1)
        self.assertFalse(result['complete'])
        self.assertFalse(result['billing_verified'])

    def test_unknown_model_and_missing_attempts_remain_unpriced(self):
        result = cost_audit({'model_calls': 2, 'model_usage': [
            {'model': 'unknown', 'usage': {'input_tokens': 5, 'output_tokens': 3}}]})
        self.assertEqual(result['unpriced_attempts'], 2)

    def test_error_attempt_is_persisted_with_stage_without_secret(self):
        from pipeline.media_acquisition import Acquisition
        from test_media_pool import make_pool
        with tempfile.TemporaryDirectory() as temp:
            pool = make_pool(Path(temp))
            acquisition = Acquisition(pool)
            acquisition.active_need = 'need-1'
            with patch('pipeline.media_acquisition.sources.request_json', side_effect=RuntimeError('429')):
                with self.assertRaises(RuntimeError):
                    acquisition.request('https://api.openai.com/v1/responses',
                        body={'model': 'gpt-5.4-nano', 'text': {'format': {'name': 'image_search_plan'}}},
                        headers={'Authorization': 'secret'})
            call = pool.payload['model_usage'][0]
            self.assertEqual(call['stage'], 'image_search_plan')
            self.assertEqual(call['need_id'], 'need-1')
            self.assertEqual(call['status'], 'error')
            self.assertTrue(acquisition.model_disabled)
            self.assertNotIn('secret', (pool.root/'media_cost_audit.json').read_text())
