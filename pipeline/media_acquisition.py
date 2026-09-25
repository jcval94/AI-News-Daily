"""Bounded acquisition worker. Public catalogues, existing model secret, no ASR."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from pydantic import ValidationError

from pipeline.licenses import assess_license
from pipeline.media_pool import Pool, normalized_license
from pipeline.media_sources.image_search import model, sources, run as images
from pipeline.media_sources.video_search import run as videos

IMAGE_SOURCES = ['commons', 'wikipedia', 'openverse', 'met', 'artic', 'loc']
VIDEO_SOURCES = ['archive', 'commons', 'peertube', 'nasa', 'youtube']


class Acquisition:
    def __init__(self, pool: Pool):
        self.pool = pool
        self.blocked_images: set[str] = set()
        self.blocked_videos: dict[str, str] = {}
        self.model_disabled = False

    def request(self, url, **kwargs):
        if url != 'https://api.openai.com/v1/responses':
            raise ValueError('Unexpected model endpoint')
        payload = self.pool.payload
        if self.model_disabled or payload['model_calls'] >= payload['budget']['model_calls']:
            raise RuntimeError('Model budget exhausted or quota failure; no additional model calls')
        payload['model_calls'] += 1
        self.pool.save()  # Attempt is charged even if the request fails or the process is killed.
        try:
            response = sources.request_json(url, **kwargs)
        except Exception as error:
            if re.search(r'quota|insufficient|401|403|429', str(error), re.I):
                self.model_disabled = True
            raise
        payload['model_usage'].append({'model': kwargs.get('body', {}).get('model'), 'usage': response.get('usage')})
        self.pool.save()
        return response

    def error(self, need, error, **fields):
        self.pool.payload['diagnostics'].append({'need_id': need['need_id'], **fields, 'error': sources.safe_error(error)})
        self.pool.save()

    def room(self):
        p = self.pool.payload
        return len(p['assets']) < p['budget']['assets'] and sum(a['size_bytes'] for a in p['assets']) < p['budget']['bytes']

    def images(self, need):
        description = ' | '.join(str(need[k]) for k in ('subject', 'period', 'geography') if need[k])
        try:
            plan, _ = model.make_plan(description, self.request)
        except ValidationError as error:
            plan, _ = model.make_plan(description, self.request, validation_feedback=sources.safe_error(error))
        if not plan.unambiguous:
            raise ValueError('Ambiguous subject; exact retrieval refused')
        try:
            entity = sources.resolve_entity(plan)
        except Exception as error:
            entity = {'status': 'unavailable', 'reason': sources.safe_error(error)}
        candidates, discovery = sources.discover(plan, [s for s in IMAGE_SOURCES if s not in self.blocked_images], entity)
        self.pool.payload['diagnostics'].append({'need_id': need['need_id'], 'kind': 'image', 'queries': plan.queries, 'discovery': discovery})
        decisions, _ = model.assess(plan, candidates, entity, self.request, editorial_pack=True)
        accepted = 0
        # Larger catalogued variants first. Every physical file is decoded again before assignment.
        candidates.sort(key=lambda c: (c.get('width') or 0) * (c.get('height') or 0), reverse=True)
        for item in candidates:
            if not self.room() or accepted >= self.pool.payload['budget']['images_per_need']:
                break
            decision = decisions.get(item['key'])
            if decision:
                decision = dict(decision)
                quote = decision.get('evidence_quote', '')
                if len(quote) > 2 and quote[0] in '\"“' and quote[-1] in '\"”' and quote[1:-1] in item['metadata'].get(decision.get('evidence_field'), ''):
                    decision['evidence_quote'] = quote[1:-1]
            reason = images.metadata_gate(plan, item, decision)
            rights = assess_license(item['source'], normalized_license(item['metadata'].get('license', '')))
            if reason or not rights['allowed']:
                self.error(need, reason or rights['reason'], candidate=item['key'], stage='eligibility')
                continue
            relation = 'context' if re.search(r'\b(memorial|commemorat\w*|cenotaph)\b', item['metadata'].get('title', ''), re.I) and not re.search(r'\b(memorial|commemorat\w*|cenotaph)\b', description, re.I) else 'exact'
            try:
                with tempfile.TemporaryDirectory(dir=self.pool.root, prefix='image-') as temp:
                    path = Path(temp) / 'source.img'
                    path.write_bytes(sources.fetch(item['image_url'], domains=sources.MEDIA_HOSTS[item['source']], max_bytes=images.MAX_BYTES))
                    media = images.inspect_file(path, min_short=80, min_long=160)
                    path = path.rename(path.with_suffix({'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}[media['format']]))
                    visual, _ = model.inspect_visual(path, self.request)
                    rejection = images.visual_gate(plan, decision, visual)
                    if rejection:
                        raise ValueError(rejection)
                    self.pool.add(path, item, need, relation=relation, evidence={
                        'field': decision['evidence_field'], 'quote': decision['evidence_quote'],
                        'value': item['metadata'][decision['evidence_field']], 'assessment': decision, 'visual': visual})
                    accepted += 1
            except Exception as error:
                self.error(need, error, candidate=item['key'], stage='download')
                if isinstance(error, sources.Blocked):
                    self.blocked_images.add(item['source'])

    def videos(self, need):
        plan, _ = videos.make_plan(need['subject'], 'semantic', self.request)
        candidates, discovery = videos.discover(plan, [s for s in VIDEO_SOURCES if s not in self.blocked_videos])
        videos.assess_candidates(plan, candidates, self.request)
        self.pool.payload['diagnostics'].append({'need_id': need['need_id'], 'kind': 'video', 'plan': plan.model_dump(), 'discovery': discovery})
        attempted, successful = set(), []
        for _ in range(6):
            if not self.room() or len(successful) >= self.pool.payload['budget']['videos_per_need']:
                break
            item = videos.next_candidate(candidates, attempted, successful, plan.events, self.blocked_videos)
            if item is None:
                break
            attempted.add(item['key'])
            # YouTube discovery omits rights; its downloaded metadata must supply them.
            if item['source'] != 'youtube' and not assess_license(item['source'], normalized_license(item.get('license', '')))['allowed']:
                self.error(need, 'Missing or incompatible catalogue license', candidate=item['key'], stage='eligibility')
                continue
            try:
                with tempfile.TemporaryDirectory(dir=self.pool.root, prefix='video-') as temp:
                    output = Path(temp)
                    duration = item.get('duration_seconds') or 0
                    mode = 'full' if 0 < duration <= 180 else 'clip'
                    result = videos.download(item, output, mode, 30, transcript_mode='off')
                    row = {**item, **result}
                    evidence = {'field': 'title_description', 'quote': item['title'],
                                'value': item['title'] + '\n' + item['description'],
                                'assessment': {k: item.get(k) for k in ('relevant', 'events', 'relevance_reason')}}
                    relation = 'context' if re.search(r'\b(memorial|commemorat\w*|cenotaph)\b', item['title'], re.I) and not re.search(r'\b(memorial|commemorat\w*|cenotaph)\b', need['subject'], re.I) else 'exact'
                    self.pool.add(output / result['path'], row, need, relation=relation, evidence=evidence)
                    successful.append(item)
            except Exception as error:
                self.error(need, error, candidate=item['key'], stage='download')
                if isinstance(error, videos.ProviderBlocked):
                    self.blocked_videos[item['source']] = videos.safe_error(error)

    def run(self):
        needs = self.pool.payload['needs']
        for need in needs[:self.pool.payload['budget']['needs']]:
            if not need['grounded']:
                self.error(need, 'Subject not present in approved narration; acquisition refused')
                continue
            for kind in (self.images, self.videos):
                if not self.room() or self.model_disabled:
                    break
                try:
                    kind(need)
                except Exception as error:
                    self.error(need, error, stage=kind.__name__)
        self.pool.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads((args.pool / 'asset_pool.json').read_text())
    Acquisition(Pool(args.pool, payload)).run()


if __name__ == '__main__':
    main()
