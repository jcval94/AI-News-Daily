"""Isolated, cacheable acquisition for Pages; never changes script approval."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline.licenses import assess_license
from pipeline.media_inspection import inspect_media
from pipeline.media_pool import ACQUISITION_VERSION, fingerprint, safe_path, sha256, write_json


def cache_key(episode: Path, maximum: int, mode: str) -> str:
    repo = Path(__file__).resolve().parents[1]
    files = set((repo / 'pipeline').glob('media*.py')) | set((repo / 'pipeline').glob('review_media*.py'))
    files |= set((repo / 'pipeline/media_sources').rglob('*.py'))
    files |= {repo / 'pipeline/licenses.py', repo / 'app/agent.py', repo / 'requirements.lock'}
    inputs = {'episode': fingerprint(episode), 'state': sha256(episode / 'run_state.json'),
              'maximum': maximum, 'mode': mode, 'version': ACQUISITION_VERSION,
              'code': {str(p.relative_to(repo)): sha256(p) for p in sorted(files)}}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def restore_cache(cache: Path, destination: Path, key: str, maximum: int) -> bool:
    try:
        meta = json.loads((cache / 'cache.json').read_text(encoding='utf-8'))
        bundle = cache / 'bundle'
        actual = {str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file()}
        if meta['key'] != key or actual != set(meta['files']) or any(p.is_symlink() for p in bundle.rglob('*')):
            return False
        for relative, digest in meta['files'].items():
            if sha256(safe_path(bundle, relative)) != digest:
                return False
        manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
        if len(manifest) < (45 if maximum >= 45 else maximum):
            return False
        if sum(float(a.get('start_seconds', 0)) < 20 for a in manifest) < min(5, maximum):
            return False
        for asset in manifest:
            if not assess_license(asset['provider'], asset['license'])['allowed']:
                return False
            if not inspect_media(safe_path(bundle, asset['file']))['ok']:
                return False
        shutil.copytree(bundle, destination)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def acquire(episode: Path, output: Path, bundle: Path, maximum: int, *, refresh=False):
    from pipeline.media_pool import retrieval_mode
    from pipeline.review_media import create_zip
    from pipeline.review_media_reuse import reuse_media
    if output.exists():
        raise ValueError('Review destination must be new')
    if not refresh and reuse_media(episode, output, bundle, minimum=45 if maximum >= 45 else maximum,
                                   opening_minimum=min(5, maximum)):
        return 'canonical_reuse'
    key = cache_key(episode, maximum, retrieval_mode())
    cache = Path('.review-media-cache') / key
    restored = not refresh and restore_cache(cache, output, key, maximum)
    if not restored:
        run_id = os.environ.get('GITHUB_RUN_ID', 'local') + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
        root = Path('.pipeline-runs') / episode.name / ('review-' + run_id)
        root.mkdir(parents=True, exist_ok=False)
        staged = root / 'scripts' / episode.name
        shutil.copytree(episode, staged)
        media = root / 'multimedia' / episode.name
        zip_path = root / 'multimedia' / 'review.zip'
        env = {**os.environ, 'MEDIA_ACQUISITION_PURPOSE': 'review'}
        command = ['--episode-dir', str(staged), '--output-dir', str(media),
                   '--zip-out', str(zip_path), '--max-media-downloads', str(maximum)]
        status = 1
        if os.environ.get('OPENAI_API_KEY'):
            try:
                status = subprocess.run([sys.executable, '-m', 'pipeline.review_media_dense_hardened', *command],
                                        env=env, timeout=1200).returncode
            except subprocess.TimeoutExpired:
                status = 124
        if status:
            shutil.rmtree(media, ignore_errors=True)
            # Consume a partial pool without repeating model calls after a model/timeout failure.
            subprocess.run([sys.executable, '-m', 'pipeline.review_media_offline_dense', *command],
                           env={**env, 'MEDIA_LIVE_ACQUISITION': '0'}, check=True, timeout=900)
        shutil.copytree(media, output)
    write_json(output / 'review_media_origin.json', {
        'schema_version': 1, 'kind': 'review_only', 'episode_date': episode.name,
        'purpose': 'review', 'cache_hit': bool(restored), 'cache_key': key,
        'source_state': json.loads((episode / 'run_state.json').read_text(encoding='utf-8')).get('status'),
        'note': 'Isolated review reconstruction; not canonical production media.',
    })
    create_zip(output, bundle)
    if not restored:
        shutil.rmtree(cache, ignore_errors=True)
        shutil.copytree(output, cache / 'bundle')
        write_json(cache / 'cache.json', {'key': key, 'files': {
            str(p.relative_to(output)): sha256(p) for p in output.rglob('*') if p.is_file()}})
    return 'review_cache' if restored else 'review_acquisition'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--zip-out', type=Path, required=True)
    parser.add_argument('--max-media-downloads', type=int, default=54)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_media_downloads <= 54:
        raise ValueError('Review media budget must be between 1 and 54')
    print(acquire(args.episode_dir, args.output_dir, args.zip_out, args.max_media_downloads, refresh=args.refresh))


if __name__ == '__main__':
    main()
