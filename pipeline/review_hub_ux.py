"""Usability layer for the existing Review Hub, independent of production gates."""
from __future__ import annotations

import re

from pipeline.pages_ux import COMMON_CSS, HELPERS_JS

REVIEW_CSS = r"""
body .wrap{max-width:1440px;padding:22px 24px 48px}
body .hero{padding:20px 22px;border-radius:16px}
body .hero h1{font-size:clamp(24px,2.6vw,32px);line-height:1.18;max-width:1000px;margin:8px 0}
body .hero .lede{font-size:15px;line-height:1.55;margin:8px 0 12px;max-width:1000px}
body .hero .eyebrow{font-size:11px}body .hero-actions .button{min-height:44px;font-size:13px;display:inline-flex;align-items:center;justify-content:center}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero{padding:14px 20px}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero h1{font-size:23px;line-height:1.25;margin:0 0 8px}
body[data-active-workspace]:not([data-active-workspace="overview"]) .hero :is(.eyebrow,.lede,.hero-actions){display:none}
body[data-active-workspace="overview"] .ux-panel-context{display:none}
body #panel-overview .overview-heading h2{margin:6px 0 0}
body .workspace-nav{top:0;margin:14px 0 18px;border-radius:12px;padding:6px 8px;box-shadow:0 6px 18px #0004}
body .hub-tabs{padding:0;gap:4px;scrollbar-width:thin}
body .hub-tab{font-size:14px;min-height:44px;padding:9px 13px;border-radius:8px}
body .workspace-nav .search-row{padding:6px 0 0;margin:6px 0 0;gap:8px}
body .workspace-nav .search-row input{font-size:14px;min-height:40px;padding:8px 10px}
body .search-count{font-size:12px}
.ux-panel-context{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;padding:4px 0 12px;color:var(--muted);font-size:13px}
.ux-panel-context strong{color:#d7ecfa;font-weight:700}
body .overview{padding-top:6px}body .overview-heading{margin-bottom:14px}
body .score-card{min-height:80px;padding:12px 14px}body .score-card strong{font-size:27px}
body .score-card span{font-size:12px}
body .decision-grid{grid-template-columns:minmax(0,1.4fr) minmax(240px,.8fr)}
body .failure-list li{grid-template-columns:86px 1fr;font-size:14px;line-height:1.65}
body .decision-actions p{font-size:14px}
body .subtab{font-size:14px;min-height:44px}
body #guion{max-width:900px}body #guion h2{margin:4px 0 16px}
body #scriptText{font-size:18px;line-height:1.85;padding:28px;max-width:78ch;margin:auto;tab-size:2}
body .script-editor-toolbar{max-width:900px;padding:12px;gap:10px}
body .script-editor-toolbar .button{font-size:13px;min-height:44px;padding:8px 12px}
body .script-editor-toolbar .button.primary{color:#eaf6ff!important;background:#21455f;border-color:#5795b8}
body .script-editor-status,body .script-editor-hint{font-size:12px;line-height:1.55}
body .script-live-metrics,body .script-live-metrics span{font-size:13px}
body .script-structure{max-width:900px}body .script-structure-head h3{font-size:15px}
body .script-structure-head p{font-size:12px}body .script-structure-track{height:58px}
body .script-structure-label{font-size:11px}body .script-structure-meta{font-size:10px}
body .script-structure-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));overflow:visible}
body .script-structure-card{min-width:0;padding:12px}
body .script-structure-card strong{font-size:13px;white-space:normal;line-height:1.4}
body .script-structure-card small{font-size:12px;line-height:1.55}
body .script-structure-badge{font-size:11px;white-space:normal;max-width:100%}
body .script-structure-detail{grid-template-columns:1fr}
body .script-structure-detail :is(h4,p){font-size:13px}
body .voice-panel,body .voice-benchmark{max-width:900px}
body :is(.voice-panel,.voice-benchmark) :is(p,small,.voice-empty,.voice-qa,.voice-chip){font-size:12px;line-height:1.55}
body .voice-head h3{font-size:15px}
body .media-origin-panel{padding:12px;margin:0 0 10px}
body .media-origin-panel h3{font-size:15px;margin:0 0 8px}
body .media-origin-chip,body .media-filter{font-size:13px;min-height:44px;padding:8px 11px}
body .media-origin-options button{font-size:13px;min-height:44px;padding:8px 11px}
body #panel-media h2{margin:12px 0}
body .media-origin-note{font-size:12px;line-height:1.5}
body .media-toolbar{margin:8px 0;gap:8px}
body .media-card{border-radius:12px}body .media-card :is(p,small){font-size:13px;line-height:1.55}
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
.ux-reading button[aria-pressed=true]{border-color:#7dd3fc;background:#21445c}
body.ux-reading .script-structure,body.ux-reading .voice-panel,body.ux-reading .voice-benchmark,body.ux-reading .ux-script-map,body.ux-reading .ux-voice{display:none}
.ux-beat-id{display:block;font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin:6px 0}
@media(max-width:760px){
  body .wrap{padding:14px 12px 36px}body .hero{padding:16px}
  body .hero h1{font-size:23px;line-height:1.22}body .hero .lede{font-size:14px}
  body .hero-actions{flex-wrap:wrap;overflow:visible;gap:8px}
  body .hero-actions .button{flex:1 1 140px;white-space:normal}
  body .workspace-nav{top:0;margin-top:10px}body .hub-tab{font-size:13px;padding:8px 11px}
  body .workspace-nav .search-row{display:flex;flex-wrap:wrap}body .search-row input{width:100%;flex:1 1 200px;min-width:0}
  body .search-count{font-size:11px}body .search-shortcut{display:none}
  body .decision-grid{grid-template-columns:1fr}body .failure-list li{grid-template-columns:1fr}
  body #scriptText{padding:18px 14px;font-size:17px;line-height:1.85}
  body .script-structure-track{height:auto;flex-wrap:wrap;gap:5px}
  body .script-structure-segment{flex:1 1 90px!important;min-height:44px}body .script-structure-meta{display:block}
  body .script-structure-cards{grid-template-columns:1fr}
  body .run-journey-kpis,body .budget-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
  body .e2e-hero h2{font-size:25px}body .run-path-chain{grid-template-columns:1fr}
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
tabs.forEach(tab=>{
  tab.addEventListener('click',()=>{updateContext();tab.scrollIntoView({block:'nearest',inline:'nearest'});});
  tab.addEventListener('keydown',()=>queueMicrotask(updateContext));
});
$$('[data-open-tab]').forEach(button=>button.addEventListener('click',updateContext));
$('#globalSearch')?.addEventListener('input',()=>requestAnimationFrame(()=>{updateContext();$$('details.ux-disclosure').forEach(box=>{if($('#globalSearch').value.trim())box.open=true;});}));
updateContext();
// Existing subtab runtime already owns activation and arrow-key handling.
$$('[data-subtab]').forEach(button=>{
  button.setAttribute('role','tab');
  const panel=$$('[data-subpanel]').find(item=>item.dataset.subpanelGroup===button.dataset.subtabGroup&&item.dataset.subpanel===button.dataset.subtab);
  if(panel){button.id=`subtab-${button.dataset.subtabGroup}-${button.dataset.subtab}`;button.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);}
});
const map=disclosure([$('.script-structure-cards')],'Ver secciones, historias y noticias');
if(map)map.classList.add('ux-script-map');
const voice=$('.voice-panel[data-tts-status="unavailable"]');
if(voice){const audio=disclosure([voice],'Escuchar narración · No disponible');audio?.classList.add('ux-voice');}
const scriptToolbar=$('.script-editor-toolbar');
if(scriptToolbar){const tools=document.createElement('div');tools.className='ux-tools ux-reading';scriptToolbar.after(tools);
  const button=toolButton('Lectura enfocada',()=>{const active=document.body.classList.toggle('ux-reading');button.setAttribute('aria-pressed',String(active));button.textContent=active?'Mostrar mapa y audio':'Lectura enfocada';});button.setAttribute('aria-pressed','false');tools.append(button);
}
// Sources and type stay visible; legal/documentary refinements are optional.
const mediaReset=$('#media-reset');if(mediaReset&&$('.media-toolbar'))$('.media-toolbar').append(mediaReset);
disclosure([$('.media-facets')],'Licencia y relación documental');
const pool=$('[data-media-pool-status]')||$('#media-pool-status');
const intro=$('.media-origin-panel p:not([role="status"])');
disclosure([pool,intro],'Adquisición y procedencia');
const mediaHeading=$('#multimedia h2');if(mediaHeading)mediaHeading.textContent='Recursos del episodio';
const beatLabels={scene:'Escena',reveal:'Revelación',complication:'Complicación',turn:'Giro',human_stakes:'Impacto humano',synthesis:'Síntesis',opening:'Introducción',reflection:'Reflexión',ending:'Cierre'};
$$('#beats .beat').forEach(beat=>{
  const heading=beat.querySelector('h3'),meta=beat.querySelector('p.muted');if(!heading||!meta)return;
  const kind=meta.textContent.split(' · ')[0].trim(),label=beatLabels[kind];if(!label)return;
  const id=document.createElement('code');id.className='ux-beat-id';id.textContent=heading.textContent;
  heading.textContent=label;heading.after(id);meta.textContent=meta.textContent.replace(kind,label);
});
// Keep the observed run first and the complete architecture one click away.
const toc=$('.e2e-toc');
if(toc){const nodes=[];let node=toc;while(node){nodes.push(node);node=node.nextElementSibling;}disclosure(nodes,'Consultar arquitectura completa del sistema');}
$$('.e2e-toc a').forEach(link=>link.addEventListener('click',()=>link.closest('details').open=true));
const stageList=$('.run-stage-list');
if(stageList){const inactive=[...stageList.querySelectorAll('.run-stage-card')].filter(card=>card.querySelector('.badge.neutral'));if(inactive.length){const box=disclosure(inactive,`${inactive.length} etapas no ejecutadas o sin observación`);stageList.append(box);}}
// Spend by step precedes provider policy. No cost values are recomputed.
const services=$('.service-grid');
if(services){const heading=services.previousElementSibling;disclosure([heading?.classList.contains('budget-section-heading')?heading:null,services],'Servicios y políticas de costo');}
const diagnostic=$('#diagnostico details.diagnostic');if(diagnostic)diagnostic.open=true;
"""


def enhance_review(document: str) -> str:
    if 'data-review-ux="2"' in document:
        return document
    if 'data-review-ux="1"' in document:
        # Recovered snapshots contain the old source HTML, not its mutated DOM.
        # Replace the old enhancement instead of stacking two runtimes.
        document = re.sub(r'<style data-review-ux="1">.*?</style>', '', document, count=1, flags=re.S)
        for match in reversed(list(re.finditer(r'<script\b[^>]*>.*?</script>', document, re.S))):
            if 'const contexts={overview:' in match[0] and 'const $ = selector' in match[0]:
                document = document[:match.start()] + document[match.end():]
                break
    labels = {"overview": "Resumen", "script": "Guion", "evidence": "Evidencia", "media": "Medios", "process": "Proceso", "budget": "Costos", "technical": "Diagnóstico"}
    for key, label in labels.items():
        document = re.sub(r'(<button\b[^>]*\bid="tab-' + key + r'"[^>]*>)[^<]*(</button>)', lambda match: match[1] + label + match[2], document, count=1)
    # Do not replace content inside the script or source evidence.
    document = document.replace('vuelve a Technical solo si necesitas', 'abre Diagnóstico si necesitas', 1)
    style = '<style data-review-ux="2">' + COMMON_CSS + REVIEW_CSS + '</style>'
    if '</head>' in document:
        document = document.replace('</head>', style + '</head>', 1)
    elif '<body>' in document:
        document = document.replace('<body>', '<body>' + style, 1)
    else:
        return document
    return document.replace('</body>', '<script data-review-ux-runtime="2">(()=>{' + HELPERS_JS + REVIEW_JS + '})();</script></body>', 1)
