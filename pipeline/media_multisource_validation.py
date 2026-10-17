"""Real-source acceptance evidence. Failed matches stay failures, never substituted."""
from __future__ import annotations
import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from pipeline.media_pool import Pool, DEFAULT_BUDGET, group_needs, write_json, provider_report
from pipeline.media_sources.video_search.plan import normalize


def benchmark(case_id):
    cases = json.loads(Path('experiments/media_retrieval_stress/multisource_cases.json').read_text(encoding='utf-8'))
    case = next(c for c in cases if c['id'] == case_id)
    root = Path('.pipeline-runs/benchmark') / case_id
    root.mkdir(parents=True, exist_ok=False)
    segment = {'mode':'media','slot_number':1,'retrieval_subject':case['label'],
               'visual_query':case['description'],'visual_role':'historical_mirror',
               'start_seconds':0,'end_seconds':10,'preferred_asset_type':'video'}
    budget = {**DEFAULT_BUDGET, 'assets':4, 'images_per_need':2, 'videos_per_need':2, 'model_calls':12}
    pool = Pool(root, {'schema_version':1,'inputs':{},'mode':'integrated','purpose':'review',
                      'budget':budget,'needs':group_needs([segment],case['label']),
                      'segments':[segment], 'assets':[], 'diagnostics':[], 'model_calls':0,
                      'model_usage':[], 'transcript_mode':'off'})
    pool.save()
    env = {**os.environ, 'MEDIA_HTTP_CACHE_DIR':str(root/'http-cache')}
    with subprocess.Popen([sys.executable,'-m','pipeline.media_acquisition','--pool',str(root)],
                          env=env, start_new_session=True) as worker:
        try:
            worker.wait(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(worker.pid, signal.SIGKILL)
            worker.wait()
    payload = json.loads((root/'asset_pool.json').read_text(encoding='utf-8'))
    results = {}
    for kind in ('image','video'):
        rows = []
        for asset in payload['assets']:
            if asset['asset_type'] != kind:
                continue
            text = normalize(asset['catalogue_evidence']['value'])
            exact = all(any(normalize(term) in text for term in group) for group in case['evidence_groups'])
            rows.append({'provider':asset['provider'],'file':asset['file'],'source_url':asset['source_url'],
                         'catalogue_exact':exact,'eligible':asset['eligible'],
                         'quality':asset['quality'],'license':asset['license']})
        results[kind] = {'success':any(r['catalogue_exact'] and r['eligible'] for r in rows),'files':rows}
    result = {'case':case,'results':results,'worker_exit':worker.returncode,
              'provider_report':provider_report(payload, []), 'model_calls':payload['model_calls'],
              'manual_visual_identity_review':'not_performed','transcript':'off','promoted':False}
    write_json(root/'validation-result.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def controls():
    from pipeline.media_sources.video_search import providers, alternatives, run
    from pipeline.media_pool import normalized_license
    from pipeline.licenses import assess_license
    from pipeline.media import download_video_shot_asset
    from pipeline.media_inspection import inspect_media
    root = Path('.pipeline-runs/source-controls')
    root.mkdir(parents=True, exist_ok=False)
    results = []
    for provider, query in [('pexels','laboratory'), ('commons','Halifax Explosion'),
                            ('archive','Apollo'), ('peertube','Blender conference'), ('nasa','Apollo 11 landing')]:
        row = {'provider':provider,'query':query,'success':False,'attempts':[],
               'purpose':'Connectivity, rights and decoder control; not an exact benchmark match'}
        try:
            if provider == 'pexels':
                record = download_video_shot_asset({'shot_number':1,'visual_query':query}, root/'pexels.mp4')
                row['success'] = bool(record and inspect_media(root/'pexels.mp4')['ok'])
                row['record'] = record
            else:
                search = providers.archive_search if provider == 'archive' else alternatives.PROVIDERS[provider]
                candidates = search(query, 8)
                for item in candidates[:8]:
                    attempt = {'id':item['id'], 'url':item['url']}
                    try:
                        if provider == 'peertube':
                            item['license'] = alternatives.peertube_rights(item)
                        elif provider == 'archive' and item.get('license') == 'unknown':
                            _, metadata = providers.archive_media(item)
                            item['license'] = metadata['license']
                        if not assess_license(provider, normalized_license(item['license']))['allowed']:
                            raise ValueError('Missing/incompatible rights: '+item['license'])
                        output = root/provider
                        output.mkdir(exist_ok=True)
                        result = run.download(item, output, 'clip', 15, transcript_mode='off')
                        attempt.update(result)
                        row['success'] = (inspect_media(output/result['path'])['ok'] and
                                          assess_license(provider, normalized_license(result['metadata'].get('license', '')))['allowed'])
                    except Exception as error:
                        attempt['error'] = providers.safe_error(error)
                    row['attempts'].append(attempt)
                    if row['success']:
                        break
        except Exception as error:
            row['error'] = providers.safe_error(error)
        results.append(row)
        write_json(root/'validation-result.json', {'controls':results,'promoted':False,'transcript':'off'})
        print(json.dumps(row, ensure_ascii=False), flush=True)


def summarize(root):
    from collections import Counter
    from pipeline.media_origin import source_origin
    rows = []
    for manifest_path in root.rglob('manifest.json'):
        if 'review-media' not in manifest_path.parts:
            continue
        media = manifest_path.parent
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        summary_path = media/'media_pool_summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
        report = {'episode':media.name, 'assets':len(manifest),
                  'providers':dict(Counter(source_origin(a)['provider'] for a in manifest)),
                  'assigned_from_pool':sum(bool(a.get('media_provenance')) for a in manifest),
                  'pool_summary':{k:v for k,v in summary.items() if k != 'diagnostics'}}
        report['acquisition_errors'] = [d for d in summary.get('diagnostics', []) if d.get('error')][:30]
        rows.append(report)
    write_json(root/'multisource-summary.json', rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case')
    parser.add_argument('--controls', action='store_true')
    parser.add_argument('--summarize', type=Path)
    args = parser.parse_args()
    if args.summarize:
        summarize(args.summarize)
    elif args.controls:
        controls()
    else:
        benchmark(args.case)


if __name__ == '__main__':
    main()
