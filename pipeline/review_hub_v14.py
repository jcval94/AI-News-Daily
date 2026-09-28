from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pipeline.core import PipelineConfig
from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v13 import build_site as _build_site_v13

CONFIG = PipelineConfig.from_env()


SCRIPT_STRUCTURE_CSS = r"""
/* v14: semantic script map. Uses pipeline-owned section metadata instead of text heuristics. */
.script-structure{max-width:850px;margin:0 auto 12px;border:1px solid var(--line);border-radius:15px;background:#0d141e;overflow:hidden}
.script-structure-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;padding:12px 13px 9px}
.script-structure-head h3{margin:0;font-size:13px;color:#e2edf7}.script-structure-head p{margin:3px 0 0;color:var(--muted);font-size:10px;line-height:1.45}
.script-structure-legend{display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end;font-size:9px;color:var(--muted)}
.script-structure-legend span{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.script-structure-dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.script-structure-dot.memory{background:#d7a9ff}.script-structure-dot.news{background:#78d8ff}
.script-structure-track{height:42px;display:flex;gap:2px;padding:0 13px 8px}
.script-structure-segment{appearance:none;border:1px solid #31445a;border-radius:8px;background:#14202d;color:#dce9f5;min-width:24px;padding:5px 6px;cursor:pointer;overflow:hidden;position:relative;text-align:left;transition:transform .15s ease,border-color .15s ease,background .15s ease}
.script-structure-segment:hover,.script-structure-segment:focus-visible{transform:translateY(-1px);border-color:#5a87aa;background:#172a3c;outline:none}
.script-structure-segment.active{border-color:#7dd3fc;background:#17344a}.script-structure-segment.memory{box-shadow:inset 0 2px 0 #d7a9ff}.script-structure-segment.news{box-shadow:inset 0 -2px 0 #78d8ff}.script-structure-segment.memory.news{box-shadow:inset 0 2px 0 #d7a9ff,inset 0 -2px 0 #78d8ff}
.script-structure-label{display:block;font-size:9px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.script-structure-meta{display:block;margin-top:2px;font-size:8px;color:#8fa2b6;white-space:nowrap}
.script-structure-cards{display:flex;gap:7px;overflow-x:auto;padding:0 13px 12px;scrollbar-width:thin}
.script-structure-card{appearance:none;flex:0 0 170px;border:1px solid #28394d;border-radius:11px;background:#111a25;color:#dce9f5;padding:9px 10px;text-align:left;cursor:pointer;transition:border-color .15s ease,transform .15s ease}
.script-structure-card:hover,.script-structure-card:focus-visible{border-color:#527ca1;transform:translateY(-1px);outline:none}.script-structure-card.active{border-color:#7dd3fc;background:#14293a}
.script-structure-card strong{font-size:10px;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.script-structure-card small{font-size:9px;color:#8fa2b6;display:block;margin-top:4px;line-height:1.35}
.script-structure-badges{display:flex;gap:4px;flex-wrap:wrap;margin-top:7px}.script-structure-badge{display:inline-flex;align-items:center;gap:3px;border-radius:999px;padding:3px 6px;font-size:8px;font-weight:700;border:1px solid #31445a;background:#0f1823;max-width:148px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.script-structure-badge.memory{border-color:#6b4a84;color:#e5c7ff;background:#21172c}.script-structure-badge.news{border-color:#315c74;color:#bfeaff;background:#102432}
.script-structure-detail{border-top:1px solid var(--line);padding:10px 13px 11px;display:grid;grid-template-columns:minmax(120px,.75fr) minmax(0,2fr);gap:11px;background:#0b121a}
.script-structure-detail[hidden]{display:none!important}.script-structure-detail h4{margin:0;font-size:11px;color:#e4eef7}.script-structure-detail p{margin:3px 0 0;font-size:10px;color:#93a5b6;line-height:1.45}.script-structure-detail-list{display:flex;gap:5px;flex-wrap:wrap;align-content:flex-start}
.script-structure-detail-chip{border:1px solid #31445a;border-radius:9px;background:#101b27;padding:5px 7px;font-size:9px;color:#b9c9d8}.script-structure-detail-chip.memory{border-color:#6b4a84;color:#e5c7ff}.script-structure-detail-chip.news{border-color:#315c74;color:#bfeaff}
#scriptText[data-structure-map="v1"]{border-left-width:5px;border-left-style:solid;transition:border-color .2s ease,box-shadow .2s ease}
#scriptText.script-section-focus{box-shadow:0 0 0 3px #7dd3fc1f,0 10px 28px #00000024}
@media(max-width:760px){.script-structure{max-width:none}.script-structure-head{display:block}.script-structure-legend{justify-content:flex-start;margin-top:8px}.script-structure-track{height:47px;padding-left:10px;padding-right:10px}.script-structure-segment{padding:5px 4px}.script-structure-meta{display:none}.script-structure-cards{padding-left:10px;padding-right:10px}.script-structure-card{flex-basis:155px}.script-structure-detail{grid-template-columns:1fr}}
"""


SCRIPT_STRUCTURE_JS = r"""
<script data-script-structure-runtime="v1">
(() => {
  const root = document.getElementById('scriptStructure');
  const scriptNode = document.getElementById('scriptText');
  if (!root || !scriptNode) return;

  const payload = __STRUCTURE_PAYLOAD__;
  const sections = Array.isArray(payload.sections) ? payload.sections : [];
  if (!sections.length) return;

  const buttons = Array.from(root.querySelectorAll('[data-script-section-index]'));
  const detail = document.getElementById('scriptStructureDetail');
  const detailTitle = document.getElementById('scriptStructureDetailTitle');
  const detailCopy = document.getElementById('scriptStructureDetailCopy');
  const detailList = document.getElementById('scriptStructureDetailList');

  const sectionColors = ['#64b5f6','#7dd3fc','#74c0fc','#8ec5ff','#88d4ab','#b7c4ff','#d7b2ff','#ffc58a'];

  function wordsWithOffsets(value) {
    const result = [];
    const regex = /\S+/gu;
    let match;
    while ((match = regex.exec(String(value || ''))) !== null) {
      result.push({start:match.index,end:match.index + match[0].length});
    }
    return result;
  }

  function locateRange(section) {
    const text = scriptNode.textContent || '';
    const startAnchor = String(section.start_anchor || '');
    const endAnchor = String(section.end_anchor || '');
    let start = startAnchor ? text.indexOf(startAnchor) : -1;
    let end = -1;
    if (start >= 0 && endAnchor) {
      const hit = text.indexOf(endAnchor, start + Math.max(1, startAnchor.length));
      if (hit >= 0) end = hit + endAnchor.length;
    }
    if (start >= 0 && end < start) {
      end = Math.min(text.length, start + Number(section.char_count || 0));
    }
    if (start < 0 || end <= start) {
      const offsets = wordsWithOffsets(text);
      if (!offsets.length) return {start:0,end:0};
      const startWord = Math.min(Math.max(0, Number(section.start_word || 0)), offsets.length - 1);
      const endWordExclusive = Math.min(
        offsets.length,
        Math.max(startWord + 1, Number(section.end_word || startWord + 1))
      );
      start = offsets[startWord].start;
      end = offsets[endWordExclusive - 1].end;
    }
    return {start:start,end:end};
  }

  function pointInTextNode(rootNode, charOffset) {
    const walker = document.createTreeWalker(rootNode, NodeFilter.SHOW_TEXT);
    let remaining = Math.max(0, charOffset);
    let node = walker.nextNode();
    let last = null;
    while (node) {
      last = node;
      const length = node.nodeValue ? node.nodeValue.length : 0;
      if (remaining <= length) return {node:node,offset:remaining};
      remaining -= length;
      node = walker.nextNode();
    }
    return last ? {node:last,offset:(last.nodeValue || '').length} : null;
  }

  function highlightRange(rangeInfo) {
    if (!rangeInfo || rangeInfo.end <= rangeInfo.start) return;
    const startPoint = pointInTextNode(scriptNode, rangeInfo.start);
    const endPoint = pointInTextNode(scriptNode, rangeInfo.end);
    if (!startPoint || !endPoint) return;
    try {
      const range = document.createRange();
      range.setStart(startPoint.node, startPoint.offset);
      range.setEnd(endPoint.node, endPoint.offset);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      const rect = range.getBoundingClientRect();
      window.scrollTo({top:Math.max(0, window.scrollY + rect.top - 150),behavior:'smooth'});
    } catch (_) {}
  }

  function renderDetail(section) {
    if (!detail || !detailTitle || !detailCopy || !detailList) return;
    detail.hidden = false;
    detailTitle.textContent = section.label || section.section_key || 'Sección';
    const bits = [];
    if (section.purpose) bits.push(section.purpose);
    bits.push(Number(section.word_count || 0).toLocaleString('es-MX') + ' palabras');
    detailCopy.textContent = bits.filter(Boolean).join(' · ');
    const chips = [];
    if (section.memory && section.memory.title) {
      chips.push('<span class="script-structure-detail-chip memory">Historia · ' + escapeHtml(section.memory.title) + '</span>');
    }
    (section.evidence || []).forEach(item => {
      const title = item.title || item.evidence_id || 'Noticia';
      const prefix = item.selected_news_index ? ('Noticia ' + item.selected_news_index) : 'Noticia';
      chips.push('<span class="script-structure-detail-chip news">' + escapeHtml(prefix + ' · ' + title) + '</span>');
    });
    detailList.innerHTML = chips.join('') || '<span class="script-structure-detail-chip">Sin historia/noticia anclada en este bloque</span>';
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  }

  function focusSection(index) {
    const section = sections[index];
    if (!section) return;
    buttons.forEach(button => button.classList.toggle('active', Number(button.dataset.scriptSectionIndex) === index));
    renderDetail(section);
    highlightRange(locateRange(section));
    scriptNode.classList.add('script-section-focus');
    window.setTimeout(() => scriptNode.classList.remove('script-section-focus'), 1300);
  }

  buttons.forEach(button => {
    button.addEventListener('click', () => focusSection(Number(button.dataset.scriptSectionIndex)));
  });

  const totalWords = Math.max(1, Number(payload.total_words || sections.reduce((sum,item)=>sum + Number(item.word_count || 0),0)));
  const stops = [];
  let cumulative = 0;
  sections.forEach((section, index) => {
    const start = Math.max(0, Math.min(100, (cumulative / totalWords) * 100));
    cumulative += Number(section.word_count || 0);
    const end = Math.max(start, Math.min(100, (cumulative / totalWords) * 100));
    const color = section.kind === 'opening' ? '#64b5f6' : section.kind === 'synthesis' ? '#ffc58a' : sectionColors[index % sectionColors.length];
    stops.push(color + ' ' + start.toFixed(2) + '%', color + ' ' + end.toFixed(2) + '%');
  });
  scriptNode.dataset.structureMap = 'v1';
  scriptNode.style.borderImage = 'linear-gradient(to bottom,' + stops.join(',') + ') 1';

  const memory = payload.narrative_memory || null;
  if (memory && memory.section_index != null) {
    const memoryButton = root.querySelector('[data-script-memory-jump]');
    if (memoryButton) {
      memoryButton.addEventListener('click', () => {
        const section = sections[Number(memory.section_index)];
        if (!section) return;
        focusSection(Number(memory.section_index));
        const base = locateRange(section);
        const offsets = wordsWithOffsets((scriptNode.textContent || '').slice(base.start, base.end));
        const wordOffset = Math.max(0, Number(memory.marker_words_from_section_start || 0));
        if (offsets.length && wordOffset < offsets.length) {
          const local = offsets[wordOffset].start;
          const target = pointInTextNode(scriptNode, base.start + local);
          if (target) {
            try {
              const range = document.createRange();
              range.setStart(target.node, target.offset);
              range.collapse(true);
              const rect = range.getBoundingClientRect();
              window.scrollTo({top:Math.max(0, window.scrollY + rect.top - 150),behavior:'smooth'});
            } catch (_) {}
          }
        }
      });
    }
  }

  document.addEventListener('reviewhub:script-content', () => {
    buttons.forEach(button => button.classList.remove('active'));
    if (detail) detail.hidden = true;
  });
})();
</script>
"""


BEAT_LABELS = {
    "scene": "Escena",
    "reveal": "Revelación",
    "complication": "Complicación",
    "turn": "Giro",
    "reflection": "Reflexión",
    "evidence": "Evidencia",
    "human_stakes": "Impacto humano",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _clean_anchor(value: str, *, head: bool, limit: int = 110) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit] if head else text[-limit:]


def build_script_structure_payload(episode_dir: Path) -> dict[str, Any] | None:
    sections_payload = _read_json(episode_dir / "script_sections.json")
    plan = _read_json(episode_dir / "episode_plan.json")
    selected = _read_json(episode_dir / "selected_news.json")
    memory_selection = _read_json(episode_dir / "narrative_memory_selection.json")

    raw_sections = sections_payload.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        return None

    plan_beats = {
        str(item.get("beat_id")): item
        for item in plan.get("beats", [])
        if isinstance(item, dict) and item.get("beat_id")
    }
    evidence_catalog = {
        str(item.get("evidence_id")): item
        for item in plan.get("evidence", [])
        if isinstance(item, dict) and item.get("evidence_id")
    }
    selected_items = [
        item for item in selected.get("items", []) if isinstance(item, dict)
    ]
    selected_by_index: dict[int, dict[str, Any]] = {}
    for fallback_index, item in enumerate(selected_items, start=1):
        try:
            index = int(item.get("selected_news_index") or fallback_index)
        except (TypeError, ValueError):
            index = fallback_index
        selected_by_index[index] = item

    memory_items = {
        str(item.get("id")): item
        for item in memory_selection.get("items", [])
        if isinstance(item, dict) and item.get("id")
    }
    narrative_meta = sections_payload.get("narrative_memory")
    narrative_meta = narrative_meta if isinstance(narrative_meta, dict) else {}
    primary_memory_id = str(
        narrative_meta.get("primary_memory_id")
        or plan.get("primary_memory_id")
        or plan.get("opening_memory_id")
        or ""
    )
    primary_memory = memory_items.get(primary_memory_id, {})
    parallel = next(
        (
            item
            for item in plan.get("narrative_parallels", [])
            if isinstance(item, dict) and str(item.get("memory_id") or "") == primary_memory_id
        ),
        {},
    )

    cumulative_words = 0
    rendered_sections: list[dict[str, Any]] = []
    for index, item in enumerate(raw_sections):
        if not isinstance(item, dict):
            continue
        section_key = str(item.get("section_key") or "")
        kind = str(item.get("kind") or "")
        beat_id = str(item.get("beat_id") or "")
        beat = plan_beats.get(beat_id, {})
        beat_kind = str(item.get("beat_kind") or beat.get("kind") or "")
        if kind == "opening" or section_key == "opening":
            label = "Introducción"
        elif kind == "synthesis" or section_key == "synthesis":
            label = "Cierre"
        else:
            label = BEAT_LABELS.get(beat_kind, "Desarrollo")

        spoken = str(item.get("spoken_text") or "")
        word_count = int(item.get("word_count") or len(spoken.split()))
        start_word = cumulative_words
        end_word = cumulative_words + word_count
        cumulative_words = end_word

        evidence: list[dict[str, Any]] = []
        for evidence_id in item.get("evidence_ids", []) if isinstance(item.get("evidence_ids"), list) else []:
            evidence_id = str(evidence_id)
            evidence_plan = evidence_catalog.get(evidence_id, {})
            try:
                news_index = int(evidence_plan.get("selected_news_index") or 0)
            except (TypeError, ValueError):
                news_index = 0
            news_item = selected_by_index.get(news_index, {})
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "selected_news_index": news_index or None,
                    "title": str(news_item.get("title") or evidence_id),
                    "source": str(news_item.get("source") or ""),
                    "url": str(news_item.get("url") or ""),
                    "role": str(evidence_plan.get("role") or ""),
                    "argument_role": str(evidence_plan.get("argument_role") or ""),
                }
            )

        carries_memory = section_key == str(narrative_meta.get("section_key") or "")
        section_memory = None
        if carries_memory:
            section_memory = {
                "id": primary_memory_id,
                "title": str(primary_memory.get("title") or primary_memory_id or "Historia"),
                "placement": str(narrative_meta.get("placement") or parallel.get("placement") or ""),
            }

        rendered_sections.append(
            {
                "index": index,
                "section_key": section_key,
                "kind": kind,
                "beat_id": beat_id or None,
                "beat_kind": beat_kind or None,
                "label": label,
                "purpose": str(beat.get("purpose") or ""),
                "word_count": word_count,
                "start_word": start_word,
                "end_word": end_word,
                "char_count": len(spoken),
                "start_anchor": _clean_anchor(spoken, head=True),
                "end_anchor": _clean_anchor(spoken, head=False),
                "memory": section_memory,
                "evidence": evidence,
            }
        )

    if not rendered_sections:
        return None

    memory_section_index = next(
        (
            int(item["index"])
            for item in rendered_sections
            if item.get("memory") is not None
        ),
        None,
    )
    memory_payload = None
    if primary_memory_id and memory_section_index is not None:
        memory_payload = {
            "id": primary_memory_id,
            "title": str(primary_memory.get("title") or primary_memory_id),
            "section_index": memory_section_index,
            "section_key": str(narrative_meta.get("section_key") or ""),
            "placement": str(narrative_meta.get("placement") or parallel.get("placement") or ""),
            "role": str(parallel.get("role") or ""),
            "purpose": str(parallel.get("purpose") or ""),
            "marker_words_from_section_start": int(
                narrative_meta.get("marker_words_from_section_start") or 0
            ),
        }

    return {
        "schema_version": 1,
        "total_words": cumulative_words,
        "sections": rendered_sections,
        "narrative_memory": memory_payload,
    }


def _structure_markup(payload: dict[str, Any]) -> str:
    sections = payload["sections"]
    total_words = max(1, int(payload.get("total_words") or 1))
    memory = payload.get("narrative_memory") or {}
    track: list[str] = []
    cards: list[str] = []

    for index, section in enumerate(sections):
        width = max(4.0, (float(section.get("word_count") or 0) / total_words) * 100.0)
        has_memory = bool(section.get("memory"))
        has_news = bool(section.get("evidence"))
        classes = ["script-structure-segment"]
        if has_memory:
            classes.append("memory")
        if has_news:
            classes.append("news")
        meta = f'{int(section.get("word_count") or 0)}p'
        track.append(
            f'<button type="button" class="{" ".join(classes)}" '
            f'data-script-section-index="{index}" style="flex:{width:.3f} 1 0" '
            f'title="{html.escape(str(section.get("label") or ""), quote=True)} · {meta}">'
            f'<span class="script-structure-label">{html.escape(str(section.get("label") or ""))}</span>'
            f'<span class="script-structure-meta">{meta}</span></button>'
        )

        badges: list[str] = []
        if has_memory:
            title = str(section["memory"].get("title") or "Historia")
            badges.append(
                '<span class="script-structure-badge memory" title="Historia / Narrative Memory">'
                f'Historia · {html.escape(title)}</span>'
            )
        for evidence in section.get("evidence", []):
            news_index = evidence.get("selected_news_index")
            title = str(evidence.get("title") or evidence.get("evidence_id") or "Noticia")
            prefix = f"Noticia {news_index}" if news_index else "Noticia"
            badges.append(
                '<span class="script-structure-badge news" title="Noticia usada en este bloque">'
                f'{html.escape(prefix)} · {html.escape(title)}</span>'
            )
        purpose = str(section.get("purpose") or "")
        card_classes = ["script-structure-card"]
        if has_memory:
            card_classes.append("memory")
        if has_news:
            card_classes.append("news")
        cards.append(
            f'<button type="button" class="{" ".join(card_classes)}" data-script-section-index="{index}">'
            f'<strong>{index + 1}. {html.escape(str(section.get("label") or ""))}</strong>'
            f'<small>{html.escape(purpose or (str(section.get("word_count") or 0) + " palabras"))}</small>'
            f'<span class="script-structure-badges">{"".join(badges)}</span></button>'
        )

    memory_jump = ""
    if memory:
        memory_jump = (
            '<button type="button" class="script-structure-badge memory" data-script-memory-jump="1" '
            'title="Ir al punto donde entra la historia">'
            f'Historia · {html.escape(str(memory.get("title") or "Narrative Memory"))}</button>'
        )

    return (
        '<section id="scriptStructure" class="script-structure" data-script-structure="v1">'
        '<div class="script-structure-head"><div><h3>Mapa del guion</h3>'
        '<p>Haz clic en un bloque para saltar al texto. La historia tiene ubicación exacta; las noticias se muestran en el beat donde el plan las utiliza.</p></div>'
        '<div class="script-structure-legend">'
        '<span><i class="script-structure-dot memory"></i>Historia</span>'
        '<span><i class="script-structure-dot news"></i>Noticia</span>'
        + memory_jump +
        '</div></div>'
        '<div class="script-structure-track" aria-label="Estructura proporcional del guion">'
        + "".join(track)
        + '</div>'
        '<div class="script-structure-cards">'
        + "".join(cards)
        + '</div>'
        '<div id="scriptStructureDetail" class="script-structure-detail" hidden>'
        '<div><h4 id="scriptStructureDetailTitle"></h4><p id="scriptStructureDetailCopy"></p></div>'
        '<div id="scriptStructureDetailList" class="script-structure-detail-list"></div>'
        '</div></section>'
    )


def apply_script_structure(
    document: str,
    *,
    structure_payload: dict[str, Any] | None,
) -> str:
    if 'data-script-structure-runtime="v1"' in document:
        return document
    if not structure_payload or not structure_payload.get("sections"):
        return document

    script_node = '<div id="scriptText" class="script" data-search-script>'
    if script_node not in document:
        raise RuntimeError("Review Hub v14 could not find Script node")

    document = document.replace(
        script_node,
        _structure_markup(structure_payload) + script_node,
        1,
    )
    document = document.replace('</style>', SCRIPT_STRUCTURE_CSS + '\n</style>', 1)
    runtime = SCRIPT_STRUCTURE_JS.replace(
        "__STRUCTURE_PAYLOAD__",
        json.dumps(structure_payload, ensure_ascii=False, separators=(",", ":")),
    )
    document = document.replace('</body>', runtime + '\n</body>', 1)
    return document


def build_site(
    *,
    episode_dir: Path,
    media_dir: Path,
    media_zip: Path,
    regression_path: Path,
    cases_path: Path,
    output_dir: Path,
    run_id: str,
    pricing_path: Path | None = None,
) -> Path:
    index_path = _build_site_v13(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
        pricing_path=pricing_path,
    )
    payload = build_script_structure_payload(episode_dir)
    document = index_path.read_text(encoding="utf-8")
    document = apply_script_structure(document, structure_payload=payload)
    index_path.write_text(document, encoding="utf-8")
    return index_path


def main() -> None:
    args = parse_args()
    result = build_site(
        episode_dir=Path(args.episode_dir),
        media_dir=Path(args.media_dir),
        media_zip=Path(args.media_zip),
        regression_path=Path(args.regression),
        cases_path=Path(args.cases),
        output_dir=Path(args.output_dir),
        run_id=str(args.run_id),
    )
    print(result)


if __name__ == "__main__":
    main()
