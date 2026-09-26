"""Reuse a validated episode bundle in Pages without another model/download run."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from pipeline.media_dedup import asset_identity_keys
from pipeline.media_inspection import inspect_media
from pipeline.media_pool import safe_path, sha256, write_json


def reuse_media(episode_dir: Path, output_dir: Path, zip_path: Path, *, minimum=45, opening_minimum=5) -> bool:
    source_root = episode_dir.resolve().parents[1]
    source = source_root / 'multimedia' / episode_dir.name
    try:
        state = json.loads((episode_dir/'run_state.json').read_text(encoding='utf-8'))
        if state.get('status') != 'approved': return False
        manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, list) or len(manifest) < minimum: return False
        if sum(float(a.get('start_seconds', 0) or 0) < 20 for a in manifest) < opening_minimum: return False
        if any(p.is_symlink() for p in source.rglob('*')): return False
        seen = set()
        for asset in manifest:
            file = safe_path(source, asset['file'])
            if asset.get('license_valid') is not True or not file.is_file() or not inspect_media(file)['ok']:
                return False
            keys = set(asset_identity_keys(asset, media_root=source))
            if not keys or seen & keys: return False
            seen.update(keys)
            provenance = asset.get('media_provenance')
            if provenance and (provenance.get('relation') != 'exact' or sha256(file) != provenance.get('rendition_id')):
                return False
        readiness_path = episode_dir/'asset_readiness.json'
        if readiness_path.is_file() and not json.loads(readiness_path.read_text(encoding='utf-8'))['gate']['ready_to_record']:
            return False
        staging_path = source_root/'integration-result.json'
        staging = json.loads(staging_path.read_text(encoding='utf-8')) if staging_path.is_file() else None
        if staging is not None and not staging.get('success'): return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if output_dir.exists():
        raise ValueError('Reuse destination must not exist')
    shutil.copytree(source, output_dir)
    write_json(output_dir/'review_media_origin.json', {
        'schema_version': 1, 'kind': 'reused_staging' if staging is not None else 'reused_episode_bundle',
        'episode_date': episode_dir.name, 'new_model_calls': 0,
        'note': 'Validated integration test; not a promoted production episode.' if staging is not None else 'Reused validated episode media; no new acquisition.',
    })
    from pipeline.review_media import create_zip
    create_zip(output_dir, zip_path)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--zip-out', type=Path, required=True)
    args = parser.parse_args()
    if not reuse_media(args.episode_dir, args.output_dir, args.zip_out):
        raise SystemExit(2)
    print('Reused validated episode multimedia; zero new model calls.')


if __name__ == '__main__': main()
