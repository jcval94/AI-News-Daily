"""Auditable acquisition token costs; unknown usage is never reported as free."""
from __future__ import annotations

import json
from pathlib import Path


def cost_audit(payload: dict) -> dict:
    rates = json.loads((Path(__file__).resolve().parents[1] / 'config/cost_rates.json').read_text(encoding='utf-8'))
    calls = []
    for original in payload.get('model_usage', []):
        call = dict(original)
        usage = call.get('usage') or {}
        model = call.get('model') or ''
        rate = rates['models'].get(model)
        if rate is None:
            rate = next((r for name, r in rates['models'].items() if model.startswith(name + '-20')), None)
        incoming, outgoing = usage.get('input_tokens'), usage.get('output_tokens')
        cached = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
        valid = all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (incoming, outgoing, cached))
        estimate = None
        if rate and valid and cached <= incoming:
            estimate = ((incoming-cached)*rate['input_per_million'] + cached*rate['cached_input_per_million'] + outgoing*rate['output_per_million']) / 1_000_000
        call['estimated_usd'] = estimate
        call['rate_source'] = rate['source'] if rate else None
        calls.append(call)
    unknown = max(0, payload.get('model_calls', 0) - len(calls)) + sum(c['estimated_usd'] is None for c in calls)
    return {'schema_version': 1, 'scope': 'documentary_acquisition_only', 'currency': 'USD',
            'rate_date': rates['as_of'], 'billing_verified': False,
            'estimated_known_usd': round(sum(c['estimated_usd'] or 0 for c in calls), 8),
            'unpriced_attempts': unknown, 'complete': unknown == 0,
            'note': 'Token-based estimate, not an invoice. Excludes editorial planning, writing, other runs and storage. Unknown attempts may have incurred charges.',
            'calls': calls}
