"""Usability layer for the existing Review Hub, independent of production gates."""
from __future__ import annotations

import re

from pipeline.pages_ux import COMMON_CSS, HELPERS_JS

REVIEW_CSS = r"""
body .wrap{max-width:1440px;padding:26px 36px 64px}
body .hero{padding:12px 0 24px;border-radius:0;border:0;background:none;box-shadow:none}
body .hero h1{font-size:clamp(28px,3.2vw,42px);line-height:1.12;max-width:980px;margin:12px 0 16px;font-weight:650}
body .hero .lede{font-size:16px;line-height:1.65;margin:8px 0 18px;max-width:82ch;color:var(--muted)}
body .hero .hero-actions{display:none}
body .hero .ux-episode-question{border:0;margin:0;background:none}
body .hero .ux-episode-question>summary{display:none}
body .hero .ux-episode-question>.ux-disclosure-body{padding:0}
body .hero .eyebrow{font-size:11px}
body :is(a,button).button:not(.secondary){background:var(--accent);border-color:var(--accent);color:#0b1820!important}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero{padding:0 0 14px;display:flex;align-items:center;gap:18px;justify-content:space-between}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero h1{font-size:15px;font-weight:500;line-height:1.4;margin:0;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero-row{flex-shrink:0}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero-row>.muted{display:none}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero :is(.eyebrow,.lede,.hero-actions,.ux-episode-question){display:none}
body[data-active-workspace="overview"] .ux-panel-context{display:none}
body #panel-overview .overview-heading h2{margin:6px 0 0}
body .workspace-nav{top:0;display:flex;align-items:center;flex-wrap:wrap;gap:8px 20px;margin:0 0 28px;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:8px 0;background:#0b0f14f5;box-shadow:none}
body .hub-tabs{flex:1 1 580px;min-width:0;padding:0;gap:2px;scrollbar-width:thin}
body .hub-tab{font-size:13px;min-height:44px;padding:9px 11px;border-radius:7px;font-weight:550}
body .hub-tab.active{background:#1b2b38;border-color:transparent;color:#c5eaf5}
body .workspace-nav .search-row{flex:0 1 240px;padding:0;margin:0;gap:8px;border:0;min-width:200px}
body .workspace-nav .search-row input{font-size:13px;min-height:44px;padding:8px 11px;min-width:0}
body .search-shortcut{display:none}
body .search-count{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
.ux-panel-context{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
body .overview{padding-top:0}body .overview-heading{margin-bottom:18px;align-items:center}
body .overview-heading h2{font-size:21px;font-weight:600}body .overview-heading .eyebrow{display:none}
body .overview-status>.badge{display:none}
body .score-strip{gap:0;margin:24px 0 30px;border-block:1px solid var(--line)}
body .score-card{min-height:80px;padding:16px 22px;border:0;border-right:1px solid var(--line);border-radius:0;background:none}
body .score-card:last-child{border-right:0}body .score-card:is(.pass,.fail){background:none;border-color:var(--line)}
body .score-card.fail strong{color:#ffb1bf}body .score-card strong{font-size:29px;font-weight:550;font-variant-numeric:tabular-nums}
body .score-card span{font-size:12px}
body .decision-grid{display:block}
body .decision-block{padding:0;border:0;background:none;border-radius:0}
body .decision-actions{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding:18px 20px;border:1px solid #354657;background:#131e29;border-radius:12px}
body .decision-actions h3{font-size:14px;margin:0;flex:1 1 100%}
body .decision-actions p{margin:0;flex:1 1 260px;color:var(--muted)}
body .decision-actions .button{margin:0;min-height:44px;font-size:13px;display:inline-flex;align-items:center}
body .decision-actions .button.secondary{background:transparent;border:1px solid #455569;color:#d4dfe9!important}
body .failure-list li{grid-template-columns:86px 1fr;font-size:14px;line-height:1.65}
body .decision-actions p{font-size:14px}
body .subtab{font-size:14px;min-height:44px}
body #guion{max-width:850px}body #guion h2{margin:4px 0 24px;font-size:28px;font-weight:600}
body #scriptText{font-size:19px;line-height:1.8;padding:26px 12px;max-width:74ch;margin:auto;tab-size:2;border:0;border-top:1px solid var(--line);border-radius:0;background:none;box-shadow:none}
body .script-editor-toolbar{max-width:850px;padding:0 0 14px;gap:10px;border:0;border-radius:0;background:none}
body .script-editor-toolbar .button{font-size:13px;min-height:44px;padding:8px 12px}
body .script-editor-toolbar .button.primary{color:#0b1820!important;background:#91d9ed;border-color:#91d9ed}
body .script-editor-toolbar .button.secondary{background:#18232e;color:#e1eaf2!important;border-color:#394c60}
body .script-editor-hint{display:none}
body .script-editor-status{width:100%}
.ux-editor-more{position:relative;color:var(--muted);font-size:13px}
.ux-editor-more>summary{border:1px solid #394c60;border-radius:8px;padding:9px 13px;min-height:44px}
.ux-editor-more>.ux-disclosure-body{position:absolute;right:0;top:calc(100% + 8px);z-index:45;display:grid;gap:6px;min-width:190px;padding:8px;background:#18232e;border:1px solid #455569;border-radius:10px;box-shadow:0 12px 32px #0007}
body .script-editor-actions .ux-reading{margin:0}
.ux-script-extras{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.ux-script-extras>.ux-disclosure{flex:1 1 280px;min-width:0;margin:0}
.ux-script-extras>.ux-disclosure[open]{flex-basis:100%}
body .script-editor-status,body .script-editor-hint{font-size:12px;line-height:1.55}
body .script-live-metrics,body .script-live-metrics span{font-size:13px}
body .script-structure{max-width:850px}body .script-structure-head h3{font-size:15px}
body .script-structure-head p{font-size:12px}body .script-structure-track{height:58px}
body .script-structure-label{font-size:11px}body .script-structure-meta{font-size:10px}
body .script-structure-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));overflow:visible}
body .script-structure-card{min-width:0;padding:12px}
body .script-structure-card strong{font-size:13px;white-space:normal;line-height:1.4}
body .script-structure-card small{font-size:12px;line-height:1.55}
body .script-structure-badge{font-size:11px;white-space:normal;max-width:100%}
body .script-structure-detail{grid-template-columns:1fr}
body .script-structure-detail :is(h4,p){font-size:13px}
body .voice-panel,body .voice-benchmark{max-width:850px}
body :is(.voice-panel,.voice-benchmark) :is(p,small,.voice-empty,.voice-qa,.voice-chip){font-size:12px;line-height:1.55}
body .voice-head h3{font-size:15px}
body .media-origin-panel{padding:0 0 14px;margin:0 0 10px;border:0;border-bottom:1px solid var(--line);background:none;border-radius:0}
body .media-origin-panel h3{font-size:15px;margin:0 0 8px}
body .media-origin-chip,body .media-filter{font-size:13px;min-height:44px;padding:8px 11px}
body .media-origin-options button{font-size:13px;min-height:44px;padding:8px 11px}
body #panel-media h2{margin:12px 0}
body .media-origin-note{font-size:12px;line-height:1.5}
body .media-toolbar{margin:8px 0;gap:8px}
body .media-card{border-radius:10px;overflow:hidden}body .media-card :is(p,small){font-size:13px;line-height:1.55}
body .media-card img,body .media-card video{aspect-ratio:16/9;object-fit:contain;background:#070d13}
body .e2e-hero h2{font-size:28px;line-height:1.2}body .e2e-hero{padding:12px 0}
body .e2e-hero p,body .e2e-intro{font-size:14px}
body .run-journey{border-top:0;padding-top:14px;margin-top:0}
body .run-path-chain{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));overflow:visible;gap:8px}
body .run-path-node{min-width:0;max-width:none}body .run-path-arrow{display:none}
body .run-path-node>small,body .run-stage-metrics small,body .run-journey-kpis small{font-size:11px}
body .run-stage-card>summary{padding:12px;font-size:14px}
body .run-stage-brief{font-size:12px}body .run-stage-card .badge{white-space:normal}
body .budget{padding-top:0}body .budget-kpis{gap:8px}
body .budget-section-heading h3{font-size:20px}body .step-cost-row small{font-size:12px;line-height:1.5}
body .coverage-item p{font-size:13px}body .budget-kpi>span{font-size:11px}
.ux-reading button[aria-pressed=true]{border-color:#7cb3c7;background:#203745}
body .subtab{background:transparent;border-radius:6px}body .subtab.active{background:#20303d;border-color:transparent}
body .source-table:not(.ux-source-trace) :is(th,td):nth-child(n+4){display:none}
body :is(.beat,.run-path-node,.budget-kpi,.service-card,.coverage-item){background:var(--panel);box-shadow:none;border-color:var(--line)}
body .run-stage-card{background:var(--panel);border-color:var(--line);box-shadow:none}
body .run-stage-card summary{background:transparent}
body.ux-reading .script-structure,body.ux-reading .voice-panel,body.ux-reading .voice-benchmark,body.ux-reading .ux-script-map,body.ux-reading .ux-voice,body.ux-reading .ux-script-extras{display:none}
.ux-beat-id{display:block;font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin:6px 0}
@media(max-width:760px){
  body .wrap{padding:18px 16px 40px}body .hero{padding:4px 0 20px}
  body .hero h1{font-size:26px;line-height:1.18}body .hero .lede{font-size:15px}
  body .hero .ux-episode-question>summary{display:list-item;list-style-position:inside;padding:10px 0;min-height:44px;color:#bed0df}
  body .hero .ux-episode-question{margin-bottom:8px}
  body .workspace-nav{top:0;margin-top:0;gap:8px;margin-bottom:22px}body .hub-tab{font-size:13px;padding:8px 11px}
  body .hub-tabs{flex-basis:100%}
  body .workspace-nav .search-row{display:flex;flex-direction:row;align-items:center;flex-wrap:nowrap;flex-basis:100%}body .workspace-nav .search-row input{width:0;flex:1 1 0;min-width:0;height:44px}
  body .search-count{font-size:11px}body .search-shortcut{display:none}
  body .ux-source-trace-tools{display:none}
  body .failure-list li{grid-template-columns:1fr}
  body .decision-actions{padding:16px}body .decision-actions .button{width:auto;flex:1 1 120px;justify-content:center}
  body .overview-heading>div:first-child{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
  body .overview-heading{gap:0;margin-bottom:14px}
  body .score-card{padding:14px}body .score-card:nth-child(2){border-right:0}body .score-card:nth-child(n+3){border-top:1px solid var(--line)}
  body .script-editor-actions{display:flex;flex-wrap:wrap;gap:8px}body .script-editor-actions>.button{width:auto}
  body .script-editor-actions>.button,body .script-editor-actions>.ux-reading,body .script-editor-actions>.ux-editor-more{flex:1 1 calc(50% - 8px)}
  .ux-reading button{width:100%}.ux-editor-more>.ux-disclosure-body{position:static;box-shadow:none;margin-top:8px}
  body[data-active-workspace]:not([data-active-workspace="overview"]) .hero h1{font-size:13px}
  body #scriptText{padding:22px 0;font-size:18px;line-height:1.8}
  body .script-live-metrics{gap:6px}body .script-live-metrics span{font-size:12px;padding:4px 7px}
  body .script-structure-track{height:auto;flex-wrap:wrap;gap:5px}
  body .script-structure-segment{flex:1 1 90px!important;min-height:44px}body .script-structure-meta{display:block}
  body .script-structure-cards{grid-template-columns:1fr}
  body .run-journey-kpis,body .budget-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  body .e2e-hero h2{font-size:25px}body .run-path-chain{grid-template-columns:1fr}
}
@media(max-width:380px){
  body .hero h1{font-size:24px}
  body .decision-actions .button{flex:1 1 0;min-width:0;white-space:normal;text-align:center;font-size:12px;padding:10px}
}
"""

REVIEW_JS = r"""
const contexts={overview:['Resumen','Estado editorial y siguiente acción'],script:['Guion','Lee, edita o descarga tu versión'],evidence:['Evidencia','Sigue la idea y comprueba sus fuentes'],media:['Medios','Revisa recursos, procedencia y licencias'],process:['Proceso','Qué ocurrió en este episodio'],budget:['Costos','Consumo observado y detalle por paso'],technical:['Diagnóstico','Jueces, historial y archivos originales']};
const context=document.createElement('div');context.className='ux-panel-context';context.setAttribute('role','status');$('.workspace-nav')?.after(context);
function updateContext(){
  const name=$('[data-tab].active')?.dataset.tab||'overview';const [label,copy]=contexts[name]||contexts.overview;
  context.replaceChildren();const strong=document.createElement('strong');strong.textContent=label;context.append(strong,document.createTextNode(copy));
  document.body.dataset.activeWorkspace=name;
}
const tabs=$$('[data-tab]');
const headline=$('.hero h1');if(headline)headline.title=headline.textContent;
const brand=$('.hero>.eyebrow');if(brand)brand.textContent='AI News Daily · Episodios';
const lede=$('.hero>.lede');
if(lede){
  const question=disclosure([lede],'Pregunta del episodio',{open:true});question.classList.add('ux-episode-question');
  const compact=window.matchMedia('(max-width:760px)');
  const fitQuestion=()=>{question.open=!compact.matches;};compact.addEventListener('change',fitQuestion);fitQuestion();
}
$$('.hero-row>.muted,.overview-status>span:not(.badge)').forEach(meta=>meta.textContent=meta.textContent.replace(/ · run .*$/,''));
$('.workspace-nav')?.setAttribute('aria-label','Navegación del episodio');
$('.hub-tabs')?.setAttribute('aria-label','Secciones del episodio');
const search=$('#globalSearch');if(search){search.placeholder='Buscar en este episodio…';search.setAttribute('aria-label','Buscar en este episodio');}
tabs.forEach(tab=>{
  tab.addEventListener('click',()=>{updateContext();tab.scrollIntoView({block:'nearest',inline:'nearest'});});
  tab.addEventListener('keydown',()=>queueMicrotask(updateContext));
});
$$('[data-open-tab]').forEach(button=>button.addEventListener('click',updateContext));
$('#globalSearch')?.addEventListener('input',()=>requestAnimationFrame(()=>{updateContext();$$('details.ux-disclosure').forEach(box=>{if($('#globalSearch').value.trim())box.open=true;});}));
updateContext();
// Existing subtab runtime already owns activation and arrow-key handling.
$$('[data-subtab]').forEach(button=>{
  if(button.dataset.subtabGroup==='evidence'&&button.dataset.subtab==='beats')button.textContent='Estructura';
  button.setAttribute('role','tab');
  const panel=$$('[data-subpanel]').find(item=>item.dataset.subpanelGroup===button.dataset.subtabGroup&&item.dataset.subpanel===button.dataset.subtab);
  if(panel){button.id=`subtab-${button.dataset.subtabGroup}-${button.dataset.subtab}`;button.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);}
});
const sourceTable=$('#fuentes .source-table');
if(sourceTable){
  const tools=document.createElement('div');tools.className='ux-tools ux-source-trace-tools';
  (sourceTable.closest('.table-wrap')||sourceTable).before(tools);
  const button=toolButton('Ver trazabilidad',()=>{const active=sourceTable.classList.toggle('ux-source-trace');button.setAttribute('aria-pressed',String(active));button.textContent=active?'Ocultar trazabilidad':'Ver trazabilidad';});
  button.setAttribute('aria-pressed','false');tools.append(button);
}
const overview=$('#overview'),nextAction=overview?.querySelector('.decision-actions');
if(nextAction){
  overview.querySelector('.score-strip')?.before(nextAction);
  nextAction.querySelector('h3').textContent='Tu siguiente paso';
  nextAction.querySelector('p').textContent='Lee el guion y dale tu voz.';
  const evaluation=nextAction.querySelector('[data-open-tab="technical"]');if(evaluation)evaluation.textContent='Ver evaluación';
  const notes=overview.querySelector('.decision-block h3');if(notes)notes.textContent='Notas de revisión';
}
const map=disclosure([$('.script-structure')],'Mapa del guion · Secciones, historias y noticias');
if(map)map.classList.add('ux-script-map');
const voice=$('.voice-panel[data-tts-status="unavailable"]');
if(voice){const audio=disclosure([voice],'Escuchar narración · No disponible');audio?.classList.add('ux-voice');}
if(map){
  const extras=document.createElement('div');extras.className='ux-script-extras';map.before(extras);extras.append(map);
  const audio=$('.ux-voice');if(audio)extras.append(audio);
  const compact=window.matchMedia('(max-width:760px)');
  const fitExtras=()=>{
    if(audio){if(compact.matches)map.querySelector('.ux-disclosure-body').append(audio);else extras.append(audio);}
    map.querySelector('summary').textContent=compact.matches?'Mapa del guion y audio':'Mapa del guion · Secciones, historias y noticias';
  };
  compact.addEventListener('change',fitExtras);fitExtras();
}
const scriptToolbar=$('.script-editor-toolbar');
if(scriptToolbar){
  const primary=new Set(['scriptEditButton','scriptSaveButton','scriptCancelButton','scriptDownloadButton']);
  const secondary=[...scriptToolbar.querySelectorAll('.script-editor-actions button')].filter(button=>!primary.has(button.id));
  const more=disclosure(secondary,'Más opciones');
  if(more){
    more.classList.replace('ux-disclosure','ux-editor-more');scriptToolbar.querySelector('.script-editor-actions').append(more);
    more.addEventListener('keydown',event=>{if(event.key==='Escape'){more.open=false;more.querySelector('summary').focus();}});
    more.addEventListener('click',event=>{if(event.target.closest('button'))more.open=false;});
    document.addEventListener('click',event=>{if(!more.contains(event.target))more.open=false;});
  }
}
if(scriptToolbar){const tools=document.createElement('div');tools.className='ux-tools ux-reading';const menu=scriptToolbar.querySelector('.ux-editor-more');if(menu)menu.before(tools);else scriptToolbar.querySelector('.script-editor-actions').append(tools);
  const button=toolButton('Lectura enfocada',()=>{const active=document.body.classList.toggle('ux-reading');button.setAttribute('aria-pressed',String(active));button.textContent=active?'Mostrar mapa y audio':'Lectura enfocada';});button.setAttribute('aria-pressed','false');tools.append(button);
}
// Sources and type stay visible; legal/documentary refinements are optional.
const mediaReset=$('#media-reset');if(mediaReset&&$('.media-toolbar'))$('.media-toolbar').append(mediaReset);
disclosure([$('.media-facets')],'Licencia y relación documental');
const pool=$('[data-media-pool-status]')||$('#media-pool-status');
const intro=$('.media-origin-panel p:not([role="status"])');
const provenance=disclosure([pool,intro],'Adquisición y procedencia');
const mediaGrid=$('#multimedia .media-grid');if(provenance&&mediaGrid)mediaGrid.after(provenance);
const acquisition=$('#multimedia>.media-toolbar')?.nextElementSibling;
if(provenance&&acquisition?.tagName==='P'&&acquisition.textContent.includes('Descargados realmente:'))provenance.querySelector('.ux-disclosure-body').append(acquisition);
const mediaHeading=$('#multimedia h2');if(mediaHeading)mediaHeading.textContent='Recursos del episodio';
if(mediaHeading&&$('.media-origin-panel'))mediaHeading.after($('.media-origin-panel'));
const beatLabels={scene:'Escena',reveal:'Revelación',complication:'Complicación',turn:'Giro',human_stakes:'Impacto humano',synthesis:'Síntesis',opening:'Introducción',reflection:'Reflexión',ending:'Cierre'};
$$('#beats .beat').forEach(beat=>{
  const heading=beat.querySelector('h3'),meta=beat.querySelector('p.muted');if(!heading||!meta)return;
  const kind=meta.textContent.split(' · ')[0].trim(),label=beatLabels[kind];if(!label)return;
  const id=document.createElement('code');id.className='ux-beat-id';id.textContent=heading.textContent;
  heading.textContent=label;heading.after(id);meta.textContent=meta.textContent.replace(kind,label);
});
// Keep the observed run first and the complete architecture one click away.
const toc=$('.e2e-toc');
if(toc){
  const nodes=[];let node=toc;while(node){nodes.push(node);node=node.nextElementSibling;}
  const manual=disclosure(nodes,'Consultar arquitectura completa del sistema');
  if(manual)manual.querySelector('.ux-disclosure-body').prepend(...[$('.e2e-hero'),$('.e2e-kpis')].filter(Boolean));
}
$$('.e2e-toc a').forEach(link=>link.addEventListener('click',()=>link.closest('details').open=true));
const stageList=$('.run-stage-list');
if(stageList){const inactive=[...stageList.querySelectorAll('.run-stage-card')].filter(card=>card.querySelector('.badge.neutral'));if(inactive.length){const box=disclosure(inactive,`${inactive.length} etapas no ejecutadas o sin observación`);stageList.append(box);}}
// Spend by step precedes provider policy. No cost values are recomputed.
const services=$('.service-grid');
if(services){
  const heading=services.previousElementSibling;
  const policies=disclosure([heading?.classList.contains('budget-section-heading')?heading:null,services],'Servicios y políticas de costo');
  const pricing=$('#panel-budget .pricing-note');if(policies&&pricing)policies.querySelector('.ux-disclosure-body').prepend(pricing);
}
const budgetHeading=$('#panel-budget h2');if(budgetHeading)budgetHeading.textContent='Costos del episodio';
const budgetLabel=$('#panel-budget .eyebrow');if(budgetLabel)budgetLabel.textContent='Consumo observado';
const diagnostic=$('#diagnostico details.diagnostic');if(diagnostic)diagnostic.open=true;
"""


def enhance_review(document: str) -> str:
    reset = re.search(r'<button\b[^>]*\bid="media-reset"[^>]*>', document)
    if reset and 'ux-button' not in reset[0]:
        tag = reset[0]
        tag = tag.replace('class="', 'class="ux-button ', 1) if 'class="' in tag else tag.replace('<button', '<button class="ux-button"', 1)
        document = document[:reset.start()] + tag + document[reset.end():]
    if 'data-review-ux="3"' in document:
        return document
    if 'data-review-ux="1"' in document or 'data-review-ux="2"' in document:
        # Recovered snapshots contain the old source HTML, not its mutated DOM.
        # Replace the old enhancement instead of stacking two runtimes.
        document = re.sub(r'<style data-review-ux="[12]">.*?</style>', '', document, count=1, flags=re.S)
        document = re.sub(r'<script data-review-ux-runtime="2">.*?</script>', '', document, count=1, flags=re.S)
        for match in reversed(list(re.finditer(r'<script\b[^>]*>.*?</script>', document, re.S))):
            if 'const contexts={overview:' in match[0] and 'const $ = selector' in match[0]:
                document = document[:match.start()] + document[match.end():]
                break
    labels = {"overview": "Resumen", "script": "Guion", "evidence": "Evidencia", "media": "Medios", "process": "Proceso", "budget": "Costos", "technical": "Diagnóstico"}
    for key, label in labels.items():
        document = re.sub(r'(<button\b[^>]*\bid="tab-' + key + r'"[^>]*>)[^<]*(</button>)', lambda match: match[1] + label + match[2], document, count=1)
    # Do not replace content inside the script or source evidence.
    document = document.replace('vuelve a Technical solo si necesitas', 'abre Diagnóstico si necesitas', 1)
    style = '<style data-review-ux="3">' + COMMON_CSS + REVIEW_CSS + '</style>'
    if '</head>' in document:
        document = document.replace('</head>', style + '</head>', 1)
    elif '<body>' in document:
        document = document.replace('<body>', '<body>' + style, 1)
    else:
        return document
    return document.replace('</body>', '<script data-review-ux-runtime="3">(()=>{' + HELPERS_JS + REVIEW_JS + '})();</script></body>', 1)
