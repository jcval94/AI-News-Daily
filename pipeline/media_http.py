"""Bounded public catalogue requests; no model calls or credentialed responses cached."""
from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit

_hosts = {}
RETRYABLE = {408, 429, 500, 502, 503, 504}


def retry_delay(value, attempt):
    try:
        return max(0., float(value))
    except (TypeError, ValueError):
        try:
            return max(0., (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return float(2 ** attempt)


def public_json(url, fetch):
    """The caller retains URL validation, redirects and response size limits."""
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or any(k.lower() in {'key', 'api_key', 'token', 'access_token'} for k, _ in parse_qsl(parsed.query)):
        return json.loads(fetch())
    directory = os.environ.get('MEDIA_HTTP_CACHE_DIR')
    cache = Path(directory) / (hashlib.sha256(url.encode()).hexdigest() + '.json') if directory else None
    if cache and cache.is_file():
        try:
            if time.time() - cache.stat().st_mtime < 86400 and cache.stat().st_size <= 8 * 1024 * 1024:
                value = json.loads(cache.read_text(encoding='utf-8'))
                if isinstance(value, dict) and not value.get('error'):
                    return value
        except (ValueError, OSError):
            pass
    state = _hosts.setdefault(parsed.hostname, {'next': 0., 'blocked': False, 'failures': 0})
    if state['blocked']:
        raise RuntimeError('Public catalogue circuit open after denial or repeated failure')
    for attempt in range(3):
        time.sleep(max(0., state['next'] - time.monotonic()))
        try:
            value = json.loads(fetch())
            if not isinstance(value, dict) or value.get('error'):
                raise ValueError('Catalogue API returned an invalid response')
        except HTTPError as error:
            state['failures'] += 1
            delay = retry_delay(error.headers.get('Retry-After'), attempt)
            state['blocked'] = error.code in {401, 403, 429} or state['failures'] >= 3
            if error.code not in RETRYABLE or attempt == 2 or delay > 30:
                raise
            state['blocked'] = False
            time.sleep(delay)
        else:
            state['failures'] = 0
            if cache:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(value), encoding='utf-8')
                temporary.replace(cache)
            return value
        finally:
            state['next'] = time.monotonic() + 0.25
    raise RuntimeError('Catalogue retry budget exhausted')
