"""Shared presentation improvements. Never changes persisted production evidence."""
from __future__ import annotations

COMMON_CSS = r"""
/* Pages UX: reuse the existing dark palette, with readable controls and less chrome. */
:root{--muted:#a3b3c4}
html{scroll-padding-top:120px}body{overflow-wrap:break-word}
[hidden]{display:none!important}
:where(button,a,input,select,summary):focus-visible{outline:3px solid #7dd3fc;outline-offset:3px}
:where(button,input,select){font:inherit}
button,summary,select{touch-action:manipulation}
button,summary{cursor:pointer}
button,input,select{min-height:44px}
summary{padding:12px;line-height:1.5}
.ux-disclosure{border:1px solid var(--line);border-radius:12px;margin:12px 0;background:var(--panel)}
.ux-disclosure>summary{font-size:14px;font-weight:700;color:var(--text)}
.ux-disclosure>.ux-disclosure-body{padding:0 14px 14px}
.ux-tools{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:12px 0}
.ux-tools button,.ux-button{border:1px solid #3a5168;border-radius:9px;padding:9px 13px;background:#122231;color:#dff3ff;font-size:14px}
.ux-tools button[aria-pressed=true]{background:#20445a;border-color:#7dd3fc}
.ux-result{font-size:13px;color:var(--muted);margin:10px 0}
.ux-empty{border:1px dashed #465b70;border-radius:12px;padding:22px;color:var(--muted)}
body main{min-width:0}body h1{font-size:clamp(26px,3vw,36px);line-height:1.15;letter-spacing:-.025em}
body .hero{padding:20px;border-radius:16px}body .hero p{font-size:14px;line-height:1.55}
body .kpi span,body .kpi small,body .eyebrow{font-size:11px}
body .kpi strong{font-size:20px;overflow-wrap:anywhere}
body .shell,body main.wrap,body>main{padding-top:22px}
body .table-wrap{max-width:100%;overscroll-behavior-x:contain}
.table-wrap:focus-visible{outline:3px solid #7dd3fc;outline-offset:3px}
@media(max-width:760px){
  html{scroll-padding-top:110px}
  body .kpis,body .kpi-row{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  body .kpi{padding:12px;min-width:0}
  body .hero{padding:16px}
  body .hero h1{font-size:26px}
  body main.wrap,body>main{padding:18px 14px 48px}
  body .topbar{flex-direction:row;align-items:center}
}
@media(prefers-reduced-motion:reduce){
  html{scroll-behavior:auto!important}
  *,*::before,*::after{animation-duration:.01ms!important;transition:none!important}
}
"""

HELPERS_JS = r"""
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
function disclosure(nodes, label, {open=false}={}) {
  nodes = nodes.filter(Boolean);
  if (!nodes.length) return null;
  const box=document.createElement('details'); box.className='ux-disclosure'; box.open=open;
  const summary=document.createElement('summary'); summary.textContent=label;
  const body=document.createElement('div'); body.className='ux-disclosure-body';
  nodes[0].before(box); box.append(summary,body); nodes.forEach(node=>body.append(node));
  return box;
}
function toolButton(label, callback) {
  const button=document.createElement('button'); button.type='button'; button.textContent=label;
  button.addEventListener('click',callback); return button;
}
function searchFeedback(input, rows, label) {
  if(!input) return;
  const result=document.createElement('p'); result.className='ux-result'; result.setAttribute('role','status');
  const empty=document.createElement('p'); empty.className='ux-empty'; empty.textContent='Sin coincidencias. Cambia los filtros o limpia la búsqueda.'; empty.hidden=true;
  input.closest('div').after(result); result.after(empty);
  const refresh=()=>{const count=rows.filter(row=>!row.hidden).length;result.textContent=`${count} de ${rows.length} ${label}`;empty.hidden=count>0;};
  input.addEventListener('input',refresh); refresh();
}
function tabSemantics(buttonSelector, panelSelector, nameAttribute, panelAttribute) {
  const buttons=$$(buttonSelector), panels=$$(panelSelector);
  if(!buttons.length) return;
  buttons[0].parentElement.setAttribute('role','tablist');
  const sync=()=>buttons.forEach((button,index)=>{
    const name=button.getAttribute(nameAttribute), panel=panels.find(item=>item.getAttribute(panelAttribute)===name);
    const active=button.classList.contains('active');
    button.id=button.id||`ux-${nameAttribute}-${index}`; button.setAttribute('role','tab');
    button.setAttribute('aria-selected',String(active)); button.tabIndex=active?0:-1;
    if(panel){panel.id=panel.id||`ux-${panelAttribute}-${index}`;button.setAttribute('aria-controls',panel.id);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);}
  });
  buttons.forEach((button,index)=>{
    button.addEventListener('click',()=>queueMicrotask(sync));
    button.addEventListener('keydown',event=>{
      if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key)) return;
      event.preventDefault();
      const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowRight'?1:buttons.length-1))%buttons.length;
      buttons[next].click(); buttons[next].focus(); buttons[next].scrollIntoView({block:'nearest',inline:'nearest'});
    });
  });sync();
}
$$('.table-wrap,.budget-table-wrap').forEach(wrap=>{wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Tabla desplazable horizontalmente');});
"""

MEMORY_CSS = r"""
body .hero{grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:18px;margin-bottom:14px;padding:0;background:none}
body .hero h1{font-size:30px;margin:8px 0}body .freshness{padding:12px;min-width:190px}
body .freshness strong{font-size:16px}
body .kpis{margin:14px 0;gap:8px}body .kpi{padding:12px}
body .source-legend{margin:8px 0;gap:8px}body .source-card{padding:10px 12px}
body .tabs{position:sticky;top:0;z-index:20;width:100%;margin:14px 0;flex-wrap:nowrap;overflow:auto;border-radius:10px;background:#0b131cf5}
body .tab-button{font-size:13px;white-space:nowrap;padding:10px 12px;min-height:44px}
body .controls{position:static;padding:10px 0;margin:0 0 12px;box-shadow:none;background:none}
body .sort-chip,body .filter-chip,body .reset-button{font-size:13px;padding:8px 11px;min-height:44px}
body .control-label,body .results-count{font-size:12px}
body .section-intro{padding:12px 14px;margin:0 0 8px}body .section-intro h2{font-size:18px}
body .section-intro p{font-size:13px}body .memory-card h3,body .news-card h3{font-size:18px;line-height:1.4}
body .memory-card .one-liner,body .news-card>p{font-size:14px;line-height:1.6}
body .chip{font-size:11px;overflow-wrap:anywhere;white-space:normal}
body .card-meta,body .score-grid span{font-size:12px}body .mechanism-row{font-size:13px;overflow-wrap:anywhere}
body .mechanism-list{max-height:420px;overflow:auto;padding-right:8px}
@media(max-width:760px){body .hero{grid-template-columns:1fr}body .hero h1{font-size:26px}body .freshness{display:flex;flex-wrap:wrap;gap:8px;align-items:center}body .kpis{grid-template-columns:repeat(3,minmax(0,1fr))}body .kpi small{font-size:11px}body .tab-button{font-size:12px}body .source-legend{grid-template-columns:1fr}}
"""

MEMORY_JS = r"""
tabSemantics('[data-memory-tab]','[data-memory-panel]','data-memory-tab','data-memory-panel');
disclosure([$('.source-legend')],'Diferencia entre historias y noticias');
disclosure([$('.kpis')],'Inventario y calidad de la biblioteca');
const categoryLine=$('[data-memory-panel="news"] .control-line');
if(categoryLine){
  const chips=[...categoryLine.querySelectorAll('[data-news-category]')];
  if(chips.length>8){
    const wrapper=document.createElement('div'); categoryLine.after(wrapper);chips.slice(7).forEach(chip=>wrapper.append(chip));
    disclosure([wrapper],`Más categorías (${chips.length-7})`);
  }
}
const mechanisms=$$('[data-memory-panel="coverage"] .mechanism-row');
if(mechanisms.length){const list=document.createElement('div');list.className='mechanism-list';list.tabIndex=0;list.setAttribute('aria-label','Mecanismos narrativos');mechanisms[0].before(list);mechanisms.forEach(row=>list.append(row));}
"""

HEALTH_JS = r"""
const checks=$$('.check-card'), healthInput=$('#healthSearch');
const priority={critical:0,warn:1,info:2,ok:3};
checks.sort((a,b)=>(priority[a.querySelector('.status')?.classList[1]]??4)-(priority[b.querySelector('.status')?.classList[1]]??4)).forEach(card=>card.parentElement.append(card));
let severity='';
const tools=document.createElement('div');tools.className='ux-tools';tools.setAttribute('aria-label','Filtrar por severidad');
const result=document.createElement('p');result.className='ux-result';result.setAttribute('role','status');
const empty=document.createElement('p');empty.className='ux-empty';empty.textContent='Sin coincidencias. Cambia la severidad o limpia la búsqueda.';
healthInput.closest('.controls').after(tools,result,empty);
const refresh=()=>{
  const q=healthInput.value.trim().toLocaleLowerCase('es');let count=0;
  checks.forEach(card=>{const hit=(!severity||card.querySelector('.status')?.classList.contains(severity))&&(!q||card.textContent.toLocaleLowerCase('es').includes(q));card.hidden=!hit;if(hit)count++;});
  result.textContent=`${count} de ${checks.length} comprobaciones · incidencias primero`;empty.hidden=count>0;
  [...tools.children].forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.severity===severity)));
};
[['','Todas'],['critical','Críticas'],['warn','Advertencias'],['ok','Correctas']].forEach(([value,label])=>{
  const count=checks.filter(card=>!value||card.querySelector('.status')?.classList.contains(value)).length;
  const button=toolButton(`${label} · ${count}`,()=>{severity=value;refresh();});button.dataset.severity=value;tools.append(button);
});
tools.append(toolButton('Limpiar',()=>{healthInput.value='';severity='';refresh();healthInput.focus();}));
healthInput.addEventListener('input',refresh);refresh();
"""

METRICS_CSS = r"""
body .summary-grid{gap:10px;margin:18px 0}body .summary-card{padding:14px}
body .chart-shell{overflow:auto}body .chart-shell svg{min-width:620px}
body .table-wrap table{min-width:850px}body .table-wrap.ux-full table{min-width:1680px}
.table-wrap:not(.ux-full) :is(th,td):nth-child(n+9){display:none}
body .table-wrap td{font-size:13px}body .table-wrap th{font-size:11px}
@media(max-width:760px){body .summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}body .sticky-col{min-width:140px}body .sticky-col small{max-width:155px}}
"""

METRICS_JS = r"""
const metricWrap=$('.table-wrap');
if(metricWrap){
  const tools=document.createElement('div');tools.className='ux-tools';metricWrap.before(tools);
  const button=toolButton('Ver métricas de producción',()=>{const full=metricWrap.classList.toggle('ux-full');button.textContent=full?'Ver resumen editorial':'Ver métricas de producción';button.setAttribute('aria-pressed',String(full));});
  button.setAttribute('aria-pressed','false');tools.append(button);
}
searchFeedback($('#metricSearch'),$$('[data-metric-row]'),'episodios');
"""

EXPERIMENTS_JS = r"""
const toolbar=$('.toolbar');
if(toolbar){
  const tools=document.createElement('div');tools.className='ux-tools';toolbar.after(tools);
  tools.append(toolButton('Restablecer filtros',()=>{const search=$('#experimentSearch');search.value='';$('#experimentName').value='';$('#experimentStatus').value='';$('#experimentSort').value='newest';search.dispatchEvent(new Event('input',{bubbles:true}));search.focus();}));
}
"""


def enhance_page(document: str, kind: str) -> str:
    """Apply once, keeping original tables, links, evidence and fallback markup."""
    if 'data-pages-ux="1"' in document:
        return document
    css, js = {
        "memory": (MEMORY_CSS, MEMORY_JS),
        "health": ("body .check-card p{font-size:14px}body .detail{font-size:12px}body .check-card:has(.critical){border-color:#a85660}", HEALTH_JS),
        "metrics": (METRICS_CSS, METRICS_JS),
        "experiments": ("body .experiment-card{margin:0}body .grid{gap:14px}body dt{font-size:12px}", EXPERIMENTS_JS),
    }[kind]
    document = document.replace('</head>', '<style data-pages-ux="1">' + COMMON_CSS + css + '</style></head>', 1)
    return document.replace('</body>', '<script>(()=>{' + HELPERS_JS + js + '})();</script></body>', 1)
