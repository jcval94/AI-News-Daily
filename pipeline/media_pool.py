"""Versioned, run-scoped editorial media pool. Python owns eligibility and assignment.

The default is off. Shadow acquires alternatives but leaves the selected media alone.
Integrated never fills a specific/critical need with stock or an invented image.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pipeline.licenses import assess_license
from pipeline.media_dedup import _normalized_source_url
from pipeline.media_inspection import inspect_media
from pipeline.schema_validation import validate_payload

CRITICAL_ROLES = {"evidence", "historical_mirror"}
DEFAULT_BUDGET = {"assets": 24, "bytes": 128 * 1024 * 1024, "seconds": 600,
                  "model_calls": 32, "needs": 8, "images_per_need": 4, "videos_per_need": 1}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def safe_path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or '\\' in relative or '..' in Path(relative).parts:
        raise ValueError('Media path must be relative and remain inside its bundle')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Media symlink escapes bundle')
    return path


def fingerprint(episode_dir: Path) -> dict:
    from pipeline.editing_style import load_editing_style
    # Hash canonical inputs, never browser drafts or model output from another run.
    result = {name: sha256(episode_dir / name) for name in
              ('script.txt', 'episode_plan.json', 'script_sections.json')}
    style = load_editing_style(Path(__file__).resolve().parents[1] / "config/editing_style.yaml")
    result['editing_style'] = hashlib.sha256(json.dumps(style, sort_keys=True).encode()).hexdigest()
    return result


def normalized_license(raw: str) -> str:
    """Normalize explicit API codes/URLs only; unknown rights stay unknown."""
    value = str(raw or '').strip()
    lower = value.lower()
    match = re.fullmatch(r'https?://creativecommons.org/(licenses|publicdomain)/([^/]+)/(\d\.\d)/?', lower)
    if match:
        group, code, version = match.groups()
        if group == 'publicdomain' and code in {'zero', 'mark'}:
            return 'CC0 ' + version if code == 'zero' else 'Public domain'
        if group == 'licenses':
            return 'CC ' + code.upper() + ' ' + version
    if re.fullmatch(r'cc[- ]?by(?:[- ]sa)?(?: \d\.\d)?', lower):
        return re.sub(r'^cc[- ]?by', 'CC BY', lower).replace('-sa', '-SA').replace(' sa', '-SA')
    return value


def is_specific(segment: dict) -> bool:
    return bool(segment.get('retrieval_subject')) or segment.get('visual_role') in CRITICAL_ROLES


def group_needs(segments: list[dict], script: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    folded_script = ' '.join(script.casefold().split())
    for segment in segments:
        if segment.get('mode') != 'media' or not is_specific(segment):
            continue
        subject = str(segment.get('retrieval_subject') or segment.get('visual_query') or '').strip()
        explicit = str(segment.get('retrieval_subject') or '').strip()
        # New explicit subjects must be literal grounded mentions in the approved script.
        grounded = not explicit or ' '.join(explicit.casefold().split()) in folded_script
        identity = {"subject": subject, "period": str(segment.get('retrieval_period', '')),
                    "geography": str(segment.get('retrieval_geography', '')),
                    "role": segment.get('visual_role') or 'context', "exact_required": True,
                    "license_policy": 'edited_public_video'}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
        need = grouped.setdefault(key, {**identity, 'need_id': key, 'slots': [], 'grounded': grounded})
        need['slots'].append(int(segment['slot_number']))
    return list(grouped.values())


def source_identity(provider: str, provider_id: str, url: str) -> str:
    # A federated numeric ID is meaningful only on its own instance.
    scope = (urlsplit(url).hostname or '') if provider == 'peertube' else ''
    identity = f'{provider}:{scope}:{provider_id or _normalized_source_url(url)}'
    return hashlib.sha256(identity.encode()).hexdigest()


def provenance(asset: dict) -> dict:
    result = {key: asset[key] for key in ('source_asset_id', 'rendition_id', 'need_id', 'relation',
              'quality', 'width', 'height', 'original_offset_seconds', 'catalogue_evidence',
              'limitation', 'sidecar_paths')}
    result['schema_version'] = 1
    validate_payload(result, 'media_provenance.schema.json')
    return result


class Pool:
    def __init__(self, root: Path, payload: dict):
        validate_payload(payload, 'asset_pool.schema.json')
        self.root, self.payload = root, payload
        self.used: set[str] = set()
        self.used_hashes: set[str] = set()

    def save(self) -> None:
        from pipeline.media_cost_audit import cost_audit
        assets = self.payload['assets']
        self.payload['summary'] = {
            'downloaded': len(assets), 'eligible': sum(a['eligible'] for a in assets),
            'assigned': len(self.used), 'exact': sum(a['relation'] == 'exact' for a in assets),
            'context': sum(a['relation'] == 'context' for a in assets),
            'low_resolution': sum(min(a['width'], a['height']) < 720 for a in assets),
            'bytes': sum(a['size_bytes'] for a in assets),
            'providers': sorted({a['provider'] for a in assets}),
            'cost_usd': None, 'cost_note': 'See recorded model token usage; no inferred dollar total',
        }
        validate_payload(self.payload, 'asset_pool.schema.json')
        write_json(self.root / 'asset_pool.json', self.payload)
        write_json(self.root / 'media_cost_audit.json', cost_audit(self.payload))

    def add(self, path: Path, row: dict, need: dict, *, relation: str, evidence: dict) -> None:
        media = inspect_media(path)
        if not media['ok']:
            raise ValueError('Downloaded media failed physical inspection')
        digest = sha256(path)
        provider = row['source']
        source_id = source_identity(provider, str(row['id']), row['url'])
        raw_license = row.get('metadata', {}).get('license') or row.get('license', '')
        license_name = normalized_license(raw_license)
        rights = assess_license(provider, license_name)
        if sum(a['size_bytes'] for a in self.payload['assets']) + path.stat().st_size > self.payload['budget']['bytes']:
            raise ValueError('Pool byte budget exhausted')
        title = row.get('metadata', {}).get('title') or row.get('title') or need['subject']
        slug = re.sub(r'[^a-z0-9]+', '-', title.casefold()).strip('-')[:70] or 'media'
        relative = f'assets/{slug}-{source_id[:12]}-{digest[:12]}{path.suffix.lower()}'
        destination = safe_path(self.root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        width, height = int(media['width']), int(media['height'])
        sidecars = {}
        if path.suffix == '.mp4':
            for name in ('metadata.json', 'transcript.json', 'most_replayed.json', 'most_replayed.svg'):
                sidecar = path.parent / name
                if sidecar.is_file():
                    target = f'metadata/{digest}/{name}'
                    safe_path(self.root, target).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(sidecar, safe_path(self.root, target))
                    sidecars[name] = target
        asset = {'source_asset_id': source_id, 'rendition_id': digest, 'need_id': need['need_id'],
                 'file': relative, 'provider': provider, 'provider_asset_id': str(row['id']),
                 'source_url': row['url'], 'title': title, 'creator': row.get('metadata', {}).get('creator') or row.get('creator', ''),
                 'license': license_name, 'license_evidence': str(raw_license),
                 'license_valid': rights['allowed'], 'requires_attribution': rights['requires_attribution'],
                 'eligible': rights['allowed'] and relation == 'exact', 'relation': relation,
                 'asset_type': media['kind'], 'width': width, 'height': height,
                 'source_width': width, 'source_height': height,
                 'remote_dimensions': {k: row.get(k) for k in ('width', 'height')},
                 'duration_seconds': float(media.get('duration_seconds') or 0),
                 'size_bytes': path.stat().st_size, 'quality': 'lowres' if min(width, height) < 720 else 'standard',
                 'original_offset_seconds': float(row.get('segment', {}).get('start_seconds') or 0),
                 'catalogue_evidence': evidence, 'sidecar_paths': sidecars,
                 'limitation': 'Catalogue-backed identity; not proof of every narrated claim. Original audio is not assigned.',
                 'transcript_mode': 'off'}
        provenance(asset)
        # Keep all unique renditions in the pool. Ranking occurs at assignment, not arrival.
        if not any(a['need_id'] == asset['need_id'] and a['rendition_id'] == digest for a in self.payload['assets']):
            self.payload['assets'].append(asset)
        self.save()

    def assign(self, segment: dict, output_dir: Path, folder: str) -> dict | None:
        from pipeline.review_media import media_filename
        need = next((n for n in self.payload['needs'] if int(segment['slot_number']) in n['slots']), None)
        if not need or not need['grounded']:
            return None
        candidates = [a for a in self.payload['assets'] if a['need_id'] == need['need_id'] and a['eligible']
                      and a['relation'] == 'exact' and a['source_asset_id'] not in self.used
                      and a['rendition_id'] not in self.used_hashes]
        # Highest physical quality within an identity, then video preference across distinct identities.
        ranked = sorted(candidates, key=lambda a: (
            a['asset_type'] == segment.get('preferred_asset_type'),
            a['width'] * a['height'], a['size_bytes']), reverse=True)
        for asset in ranked:
            try:
                source = safe_path(self.root, asset['file'])
                rights = assess_license(asset['provider'], asset['license'])
                if not rights['allowed'] or sha256(source) != asset['rendition_id']:
                    raise ValueError('Cached media hash or license is invalid')
                decoded = inspect_media(source)
                if not decoded['ok'] or (decoded['width'], decoded['height']) != (asset['width'], asset['height']):
                    raise ValueError('Cached media physical dimensions are invalid')
                relative = f'{folder}/{media_filename(segment, extension=source.suffix)}'
                destination = safe_path(output_dir, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                record = {**asset, 'shot_number': int(segment['slot_number']), 'file': relative,
                          'visual_query': segment.get('visual_query', ''), 'errors': [],
                          'license_valid': rights['allowed'], 'requires_attribution': rights['requires_attribution']}
                record['media_provenance'] = provenance(asset)
                # Copy selected sidecars; never reference the working pool from the portable bundle.
                selected_sidecars = {}
                for name, path in asset['sidecar_paths'].items():
                    target = f'metadata/{asset["rendition_id"]}/{name}'
                    safe_path(output_dir, target).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(safe_path(self.root, path), safe_path(output_dir, target))
                    selected_sidecars[name] = target
                record['media_provenance']['sidecar_paths'] = selected_sidecars
                self.used.add(asset['source_asset_id'])
                self.used_hashes.add(asset['rendition_id'])
                self.save()
                return record
            except (ValueError, OSError) as error:
                self.payload['diagnostics'].append({'source_asset_id': asset['source_asset_id'], 'error': str(error)})
        self.save()
        return None


def retrieval_mode() -> str:
    mode = os.environ.get('MEDIA_RETRIEVAL_MODE', 'off')
    if mode not in {'off', 'shadow', 'integrated'}:
        raise ValueError('MEDIA_RETRIEVAL_MODE must be off, shadow or integrated')
    return mode


def prepare_pool(episode_dir: Path, output_dir: Path, segments: list[dict], *, offline=False) -> Pool | None:
    mode = retrieval_mode()
    if mode == 'off':
        return None
    state = json.loads((episode_dir / 'run_state.json').read_text(encoding='utf-8'))
    if state.get('status') != 'approved':
        raise ValueError('Media acquisition requires an approved episode')
    run_root = episode_dir.resolve().parents[1]
    # Prevent canonical mutation even when manually invoked with an opt-in flag.
    if '.pipeline-runs' not in run_root.parts or not output_dir.resolve().is_relative_to(run_root):
        raise ValueError('Opt-in media retrieval requires an isolated .pipeline-runs run')
    root = run_root / 'media-pool'
    inputs = fingerprint(episode_dir)
    path = root / 'asset_pool.json'
    if path.exists():
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload['inputs'] != inputs:
            raise ValueError('Stale media pool: approved inputs or editing style changed; use a new run')
        pool = Pool(root, payload)
        if offline:
            return pool
        if payload['segments'] != segments:
            raise ValueError('Media plan changed in existing pool; use a new run')
        return pool
    budget = dict(DEFAULT_BUDGET)
    pool = Pool(root, {'schema_version': 1, 'inputs': inputs, 'mode': mode, 'budget': budget,
                'needs': group_needs(segments, (episode_dir / 'script.txt').read_text(encoding='utf-8')),
                'segments': segments, 'assets': [], 'diagnostics': [], 'model_calls': 0,
                'model_usage': [], 'summary': {}, 'transcript_mode': 'off'})
    pool.save()
    if offline:
        pool.payload['diagnostics'].append({'error': 'Offline fallback: no prior pool; no model calls'})
        pool.save()
        return pool
    started = time.monotonic()
    with subprocess.Popen([sys.executable, '-m', 'pipeline.media_acquisition', '--pool', str(root)],
                          start_new_session=True, env={**os.environ, "MEDIA_POOL_WORKER": "1"}) as worker:
        try:
            worker.wait(timeout=budget['seconds'])
        except subprocess.TimeoutExpired:
            os.killpg(worker.pid, signal.SIGKILL)
            worker.wait()
    for prefix in ('image-*', 'video-*', 'video-download-*'):
        for temporary in root.glob(prefix):
            if temporary.is_dir():
                shutil.rmtree(temporary)
    pool = Pool(root, json.loads(path.read_text(encoding='utf-8')))
    pool.payload['elapsed_seconds'] = round(time.monotonic() - started, 2)
    if worker.returncode:
        pool.payload['diagnostics'].append({'error': 'Acquisition stopped; partial validated pool retained', 'exit_code': worker.returncode})
    pool.save()
    return pool


def finish_assignment(pool: Pool | None, manifest: list[dict], segments: list[dict], original: list[dict], output_dir: Path) -> list[dict]:
    """Refill lost slots once from the already validated pool; retain every planned cue."""
    if pool is None:
        return segments
    by_slot = {int(s['slot_number']): s for s in segments}
    assigned = {int(a['shot_number']) for a in manifest}
    if retrieval_mode() == 'integrated':
        for segment in original:
            number = int(segment['slot_number'])
            if segment.get('mode') != 'media' or number in assigned:
                continue
            record = pool.assign(segment, output_dir, 'recovered')
            if record:
                record.update({k: segment.get(k) for k in ('start_seconds', 'end_seconds', 'on_screen_text', 'reason')})
                manifest.append(record)
                by_slot[number] = {**segment, 'file': record['file'], 'asset_type': record['asset_type']}
            else:
                by_slot[number] = {**segment, 'file': '', 'retrieval_status': 'unresolved'}
    pool.save()
    summary = {**pool.payload['summary'], 'mode': retrieval_mode(),
               'baseline_selected': len(manifest), 'model_calls': pool.payload['model_calls'],
               'elapsed_seconds': pool.payload.get('elapsed_seconds'),
               'unresolved_slots': [n for n, s in by_slot.items() if s.get('retrieval_status') == 'unresolved'],
               'diagnostics': pool.payload['diagnostics']}
    write_json(output_dir / 'media_pool_summary.json', summary)
    from pipeline.media_cost_audit import cost_audit
    write_json(output_dir / 'media_cost_audit.json', cost_audit(pool.payload))
    return sorted(by_slot.values(), key=lambda s: s['slot_number'])
