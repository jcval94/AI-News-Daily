"""Independent, frozen 12-case benchmark; retrieval gates are not ground truth."""
from __future__ import annotations
import argparse
import json
import re
import unicodedata
from pathlib import Path
from types import SimpleNamespace
from experiments.image_search import run as images
from experiments.video_search import run as videos

ROOT = Path(__file__).resolve().parents[2]


def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(value)).lower()
                                          if not unicodedata.combining(c))).strip()


def evidence_matches(case, row):
    # Never match the query, model explanation, plan or requested description.
    metadata = row.get('metadata', {})
    fields = [row.get('title', ''), row.get('description', '')]
    fields += [metadata.get(k, '') for k in ('title', 'description', 'subjects', 'date')]
    text = ' ' + normalize(' '.join(map(str, fields))) + ' '
    return all(any(' ' + normalize(alias) + ' ' in text for alias in group)
               for group in case['evidence_groups'])


def audit(case, modality, manifest, candidates):
    downloaded = [x for x in manifest.get('items', []) if x.get('status') == 'downloaded']
    matches = [x for x in downloaded if evidence_matches(case, x)]
    return dict(case_id=case['id'], label=case['label'], modality=modality,
                description=case['description'], expected=case,
                candidates=len(candidates), textual_candidate_matches=sum(evidence_matches(case, x) for x in candidates),
                downloaded=len(downloaded), downloaded_with_literal_evidence=len(matches),
                exact_success=None, review_status='human_review_required',
                note='Literal evidence is a review aid, not proof of exact identity or event depiction.',
                pipeline_summary=manifest.get('summary', {}), fatal_error=manifest.get('fatal_error'),
                media=[dict(key=x['key'], url=x['url'], path=x['path'],
                            evidence_match=evidence_matches(case, x),
                            title=x.get('title') or x.get('metadata', {}).get('title'),
                            metadata=x.get('metadata'), assessment=x.get('assessment'),
                            duration_seconds=x.get('media', {}).get('duration_seconds')) for x in downloaded])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--modality', choices=['images','videos'], required=True)
    args=parser.parse_args()
    cases=json.loads((Path(__file__).with_name('cases.json')).read_text())
    case=next(c for c in cases if c['id']==args.case)
    output=ROOT / ('image-search-output' if args.modality=='images' else 'video-search-output') / 'stress'
    output.mkdir(parents=True,exist_ok=False)
    description=case['description']
    if args.modality=='images':
        description += (' Solo fotografías reales de esta persona, identificada expresamente en la ficha.' if case['kind']=='person' else
                        ' Solo documentos visuales identificados expresamente con este evento exacto. No lugares, personas, objetos o mapas meramente relacionados; no recreaciones modernas ni imágenes generadas.')
        images.execute(SimpleNamespace(description=description,count=1,sources='commons,met,artic,loc'),output)
    else:
        description += ' Busca un video corto dedicado específicamente a este referente; no menciones incidentales ni compilaciones generales.'
        videos.execute(SimpleNamespace(description=description,count=1,sources='youtube,archive',mode='full',
                                       clip_seconds=15,planner='semantic',transcript='off'),output)
    manifest=json.loads((output/'manifest.json').read_text())
    candidates=json.loads((output/'candidates.json').read_text()) if (output/'candidates.json').exists() else []
    result=audit(case,args.modality,manifest,candidates)
    (output/'benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    # Add benchmark to the integrity manifest after the retrieval report finished.
    import hashlib
    with (output/'SHA256SUMS').open('a') as f:
        f.write(hashlib.sha256((output/'benchmark.json').read_bytes()).hexdigest()+'  benchmark.json\n')
    print('BENCHMARK '+json.dumps({k:v for k,v in result.items() if k not in {'expected','media'}},ensure_ascii=False),flush=True)
    # A completed negative is valid benchmark data. Success is evaluated separately.
    return 0

if __name__=='__main__':
    raise SystemExit(main())
