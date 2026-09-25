"""Controlled acceptance fixture: approved Plato narration, real catalogue anchor.

Not a replacement semantic planner. Does not call a model or invent an approval.
The storyboard explicitly labels generic B-roll as context; only the catalogue
portrait is historical evidence. This plan is isolated and never promoted.
"""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

from pipeline.media_pool import Pool, DEFAULT_BUDGET, fingerprint, group_needs
from pipeline.media_sources.image_search import sources, alternatives, model, run as images


def seed(episode: Path, media: Path) -> Pool:
    from pipeline.review_media_density import install_density_policy
    install_density_policy()
    from pipeline import review_media as base
    from pipeline.review_media_offline import build_deterministic_plan
    script=(episode/'script.txt').read_text(encoding='utf-8')
    if 'Platón' not in script:
        raise ValueError('Controlled replay requires the actual approved Plato narration')
    sections=json.loads((episode/'script_sections.json').read_text(encoding='utf-8'))
    ranges=base.section_timeline(sections,base.CONFIG.words_per_second)
    slots=base.build_review_candidate_slots(ranges)
    plan=build_deterministic_plan(episode_plan=json.loads((episode/'episode_plan.json').read_text(encoding='utf-8')),
          selected_news=json.loads((episode/'selected_news.json').read_text(encoding='utf-8')),candidate_slots=slots,max_media_downloads=54)
    plan=base.select_spread_media_budget(plan,max_media_downloads=54)
    # Curated storyboard: stock illustrates concepts, it cannot claim to show exact research.
    for segment in plan:
        if segment.get('mode')=='media':
            segment['visual_role']='context'
            segment['director_note']='Conceptual B-roll; does not depict the exact study or historical event.'
    target_range=next(r for r in ranges if 'Platón' in str(r)) if any('Platón' in str(r) for r in ranges) else None
    # Use the actual aligned section text to locate the reference, not an arbitrary new event.
    if target_range is None:
        source_section=next(s for s in sections['sections'] if 'Platón' in json.dumps(s,ensure_ascii=False))
        target_range=next(r for r in ranges if r['section_key']==source_section['section_key'])
    eligible=[s for s in plan if s.get('mode')=='media' and s['start_seconds']>=max(20,target_range['start_seconds']) and s['start_seconds']<target_range['end_seconds']]
    if not eligible: raise ValueError('No planned media cue in the section mentioning Plato')
    chosen=eligible[0]
    chosen.update(retrieval_subject='Platón',visual_query='Ancient bust of Plato',visual_role='historical_mirror',preferred_asset_type='image',
                  reason='Catalogue-attributed ancient bust of Plato, discussed in approved narration')
    needs=group_needs(plan,script)
    root=episode.resolve().parents[1]/'media-pool'
    pool=Pool(root,{'schema_version':1,'mode':'integrated','inputs':fingerprint(episode),'budget':dict(DEFAULT_BUDGET),
        'needs':needs,'segments':plan,'assets':[],'diagnostics':[{'acceptance_mode':'controlled_catalogue_replay','semantic_live_status':'blocked_no_credits','storyboard_authority':'isolated curated acceptance fixture; not canonical'}],
        'model_calls':0,'model_usage':[],'transcript_mode':'off'})
    pool.save()
    request=model.Plan(subject='Plato',kind='person',unambiguous=True,interpretation='Catalogued ancient portrait of Plato; not a photograph of the living person',
        queries=['Plato'],museum_query='Plato',date_start=None,date_end=None,allowed_types=['historical_artwork','object_photo'])
    entity=sources.resolve_entity(request)
    if entity.get('status')!='resolved': raise ValueError('No unambiguous catalogue entity for Plato')
    errors=[]
    for discover in (sources.commons,alternatives.wikipedia):
        try: candidates=discover(request,entity)
        except Exception as error:
            errors.append(sources.safe_error(error));continue
        for item in candidates:
            if not item.get('entity_anchor'): continue
            if images.SYNTHETIC.search(' '.join(item['metadata'].values())): continue
            try:
                with tempfile.TemporaryDirectory(dir=root) as tmp:
                    file=Path(tmp)/'source.img'
                    file.write_bytes(sources.fetch(item['image_url'],domains=sources.MEDIA_HOSTS[item['source']],max_bytes=images.MAX_BYTES))
                    decoded=images.inspect_file(file,min_short=80,min_long=160)
                    file=file.rename(file.with_suffix({'JPEG':'.jpg','PNG':'.png','WEBP':'.webp'}[decoded['format']]))
                    evidence={'field':'wikidata_P18','quote':entity['id'],'value':entity['id'],
                              'entity':entity,'catalogue':item['metadata'],'method':'Unique human entity exact canonical name and nondeprecated P18 file link; no visual classifier claim'}
                    pool.add(file,item,needs[0],relation='exact',evidence=evidence)
                    if pool.payload['assets'][-1]['eligible']:
                        return pool
            except Exception as error: errors.append(sources.safe_error(error))
    raise ValueError('No eligible downloadable anchored Plato depiction: '+'; '.join(errors))
