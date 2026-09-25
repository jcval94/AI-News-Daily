"""Replay an approved episode through opt-in retrieval and the entire editing handoff.

No canonical writes, no promotion, no Resolve installation required. Missing media
fails the real readiness gate. A failed run is retained for diagnosis, never greened.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline.media_pool import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalogue-replay',action='store_true')
    parser.add_argument('--date',default='2026-09-04')
    parser.add_argument('--run-id',default=os.environ.get('GITHUB_RUN_ID','local'))
    args=parser.parse_args()
    root=Path('.pipeline-runs') / args.date / ('media-integration-'+args.run_id)
    root.mkdir(parents=True,exist_ok=False)
    episode=root/'scripts'/args.date
    shutil.copytree(Path('scripts')/args.date,episode)
    media=root/'multimedia'/args.date
    bundle=root/'multimedia'/f'multimedia-{args.date}.zip'
    env={**os.environ,'MEDIA_RETRIEVAL_MODE':'integrated'}
    if args.catalogue_replay:
        from pipeline.media_catalogue_replay import seed
        seed(episode,media)
    builder='pipeline.review_media_offline_dense' if args.catalogue_replay else 'pipeline.review_media_dense_hardened'
    subprocess.run([sys.executable,'-m',builder,'--episode-dir',str(episode),
                    '--output-dir',str(media),'--zip-out',str(bundle),'--max-media-downloads','54'],env=env,check=True)
    from pipeline.production_script import create_production_script
    from pipeline.recording_pack import write_recording_pack
    from pipeline.recording_ingest import write_ingest_contract
    from pipeline.virtual_timeline import write_virtual_timeline
    from pipeline.placeholder_media import write_placeholder_media
    from pipeline.otio_export import write_otio
    from pipeline.resolve_bridge import write_resolve_plan
    from pipeline.preview_render import write_preview
    from pipeline.asset_readiness import write_asset_readiness
    from pipeline.run import CONFIG
    from pipeline.review_hub_v13 import build_site
    create_production_script(target_date=args.date,scripts_root=root/'scripts',multimedia_root=root/'multimedia')
    write_recording_pack(episode_dir=episode,media_dir=media,words_per_second=CONFIG.words_per_second)
    write_ingest_contract(episode_dir=episode)
    write_virtual_timeline(episode_dir=episode,media_dir=media)
    write_placeholder_media(episode_dir=episode)
    write_otio(episode_dir=episode)
    write_resolve_plan(repo_root=root,episode_dir=episode)
    write_preview(repo_root=root,episode_dir=episode,width=640,height=360,fps=10)
    _,_,readiness=write_asset_readiness(repo_root=root,episode_dir=episode,policy_path=Path('config/asset_readiness.yaml'),enforce=False)
    # Prove relocation: regenerate only the machine-specific Resolve mapping after extraction.
    relocated=root.parent/(root.name+'-relocated')
    shutil.copytree(root,relocated,ignore=shutil.ignore_patterns('media-pool'))
    moved_episode=relocated/'scripts'/args.date
    write_resolve_plan(repo_root=relocated,episode_dir=moved_episode)
    _,_,relocated_readiness=write_asset_readiness(repo_root=relocated,episode_dir=moved_episode,policy_path=Path('config/asset_readiness.yaml'),enforce=False)
    build_site(episode_dir=episode,media_dir=media,media_zip=bundle,
               regression_path=Path('editorial-regression.json'),cases_path=Path('evals/editorial/cases.json'),
               output_dir=root/'review-site',run_id=args.run_id)
    manifest=json.loads((media/'manifest.json').read_text())
    selected=len(manifest);opening=sum(float(a.get('start_seconds',0))<20 for a in manifest)
    pool=json.loads((root/'media-pool/asset_pool.json').read_text())
    assigned=sum('media_provenance' in a for a in manifest)
    success=selected>=45 and opening>=5 and readiness['gate']['ready_to_record'] and relocated_readiness['gate']['ready_to_record'] and assigned>0
    result={'schema_version':1,'episode_date':args.date,'run_id':args.run_id,'sha':os.environ.get('GITHUB_SHA'),
            'selected':selected,'opening':opening,'pool':pool['summary'],'assigned_from_pool':assigned,
            'readiness':readiness['gate'],'relocated_readiness':relocated_readiness['gate'],
            'pages_panel': 'id="media-pool-status"' in (root/'review-site/index.html').read_text(),
            'acceptance_mode':'controlled_catalogue_replay' if args.catalogue_replay else 'live_semantic',
            'semantic_live_status':'blocked_no_credits' if args.catalogue_replay else 'tested',
            'success':success,'promoted':False,'resolve_local_acceptance':'pending','transcript':'off'}
    write_json(root/'integration-result.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not success:
        raise SystemExit('Integration acceptance failed; inspect preserved artifacts')


if __name__=='__main__': main()
