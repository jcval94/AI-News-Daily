from __future__ import annotations

import json
from pathlib import Path

from pipeline.core import PipelineConfig
from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v12 import build_site as _build_site_v12

CONFIG = PipelineConfig.from_env()


SCRIPT_PRODUCTIVITY_CSS = r"""
/* v13: low-cost script productivity helpers: live metrics, diff and 5-save history. */
.script-live-metrics{max-width:850px;margin:0 auto 10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:11px}
.script-live-metrics span{display:inline-flex;align-items:center;gap:4px;border:1px solid #29394d;border-radius:999px;background:#111a25;padding:5px 9px}.script-live-metrics strong{color:#dce9f5}.script-live-metrics .delta-positive{color:#9ee6bd}.script-live-metrics .delta-negative{color:#ffb8c4}
.script-tool-panel{max-width:850px;margin:0 auto 10px;border:1px solid var(--line);border-radius:14px;background:#0d141e;overflow:hidden}.script-tool-panel[hidden]{display:none!important}.script-tool-panel-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:11px 13px;border-bottom:1px solid var(--line)}.script-tool-panel-head h3{margin:0;font-size:13px}.script-tool-panel-head button{appearance:none;border:0;background:transparent;color:var(--muted);font-size:18px;cursor:pointer;padding:2px 7px}.script-tool-panel-body{padding:12px 13px;max-height:430px;overflow:auto}
.script-diff-summary{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:9px;font-size:11px;color:var(--muted)}.script-diff-summary span{border:1px solid #29394d;border-radius:999px;padding:4px 8px}.script-diff{font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap}.script-diff-line{display:grid;grid-template-columns:24px 1fr;gap:7px;padding:2px 6px;border-radius:5px}.script-diff-line.add{background:#12312666;color:#b9f3ce}.script-diff-line.del{background:#3a182166;color:#ffc0ca}.script-diff-line.same{color:#8797a9}.script-diff-line b{user-select:none;opacity:.72}
.script-history-list{display:grid;gap:7px}.script-history-item{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;border:1px solid #29394d;border-radius:11px;background:#111a25;padding:10px}.script-history-item h4{font-size:12px;margin:0 0 3px}.script-history-item p{font-size:10px;color:var(--muted);margin:0}.script-history-item button{appearance:none;border:1px solid #35506b;border-radius:8px;background:#152638;color:#d7ebfa;padding:6px 9px;font:inherit;font-size:11px;cursor:pointer}.script-history-original{border-style:dashed}.script-history-empty{color:var(--muted);font-size:12px;margin:0}
@media(max-width:760px){.script-live-metrics{max-width:none}.script-tool-panel{max-width:none}.script-history-item{grid-template-columns:1fr}.script-history-item button{width:100%;min-height:39px}}
"""


SCRIPT_PRODUCTIVITY_JS = r"""
<script data-script-productivity-runtime="v1">
(() => {
  const scriptNode = document.getElementById('scriptText');
  const editActions = document.querySelector('.script-editor-actions');
  const saveButton = document.getElementById('scriptSaveButton');
  const restoreButton = document.getElementById('scriptRestoreButton');
  const wordsNode = document.getElementById('scriptLiveWords');
  const durationNode = document.getElementById('scriptLiveDuration');
  const deltaNode = document.getElementById('scriptLiveDelta');
  const diffButton = document.getElementById('scriptDiffButton');
  const historyButton = document.getElementById('scriptHistoryButton');
  const diffPanel = document.getElementById('scriptDiffPanel');
  const historyPanel = document.getElementById('scriptHistoryPanel');
  const diffBody = document.getElementById('scriptDiffBody');
  const historyBody = document.getElementById('scriptHistoryBody');
  if (!scriptNode || !editActions || !saveButton || !wordsNode || !durationNode || !deltaNode) return;

  const episodeKey = __EPISODE_KEY__;
  const originalText = __ORIGINAL_TEXT__;
  const wordsPerSecond = __WORDS_PER_SECOND__;
  const editorStorageKey = 'ai-news-daily:script-editor:v1:' + episodeKey;
  const historyStorageKey = 'ai-news-daily:script-history:v1:' + episodeKey;
  const MAX_HISTORY = 5;

  const currentText = () => scriptNode.textContent || '';
  const wordCount = value => {
    const trimmed = String(value || '').trim();
    return trimmed ? trimmed.split(/\s+/u).length : 0;
  };
  const formatDuration = words => {
    const seconds = Math.max(0, Math.round(words / Math.max(wordsPerSecond, 0.01)));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return h ? (h + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0')) : (m + ':' + String(s).padStart(2,'0'));
  };
  const fmt = value => {
    try { return new Intl.DateTimeFormat('es-MX', {dateStyle:'medium', timeStyle:'short'}).format(new Date(value)); }
    catch (_) { return String(value || ''); }
  };
  const escapeHtml = value => String(value || '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));

  function updateMetrics() {
    const words = wordCount(currentText());
    const originalWords = wordCount(originalText);
    const delta = words - originalWords;
    wordsNode.textContent = words.toLocaleString('es-MX');
    durationNode.textContent = '~' + formatDuration(words);
    deltaNode.textContent = delta === 0 ? 'sin cambio' : ((delta > 0 ? '+' : '') + delta.toLocaleString('es-MX') + ' palabras');
    deltaNode.classList.toggle('delta-positive', delta > 0);
    deltaNode.classList.toggle('delta-negative', delta < 0);
  }

  function readHistory() {
    try {
      const value = JSON.parse(localStorage.getItem(historyStorageKey) || '[]');
      return Array.isArray(value) ? value.filter(item => item && typeof item.text === 'string').slice(0, MAX_HISTORY) : [];
    } catch (_) {
      return [];
    }
  }

  function writeHistory(items) {
    try {
      localStorage.setItem(historyStorageKey, JSON.stringify(items.slice(0, MAX_HISTORY)));
      return true;
    } catch (_) {
      return false;
    }
  }

  function readEditorRecord() {
    try {
      const value = JSON.parse(localStorage.getItem(editorStorageKey) || 'null');
      return value && typeof value === 'object' ? value : null;
    } catch (_) {
      return null;
    }
  }

  function addHistorySnapshot(textValue, savedAt, source='save') {
    const history = readHistory();
    if (history.length && history[0].text === textValue) {
      history[0].savedAt = savedAt || history[0].savedAt;
      history[0].source = source;
      writeHistory(history);
      return;
    }
    history.unshift({
      id: String(savedAt || Date.now()) + ':' + Math.random().toString(36).slice(2,8),
      text: String(textValue || ''),
      savedAt: savedAt || new Date().toISOString(),
      words: wordCount(textValue),
      source,
    });
    writeHistory(history.slice(0, MAX_HISTORY));
  }

  function seedCurrentSavedVersion() {
    if (readHistory().length) return;
    const record = readEditorRecord();
    if (record && typeof record.savedText === 'string' && record.savedAt) {
      addHistorySnapshot(record.savedText, record.savedAt, 'save');
    }
  }

  function closePanels(except=null) {
    [[diffPanel,'diff'],[historyPanel,'history']].forEach(([panel,name]) => {
      if (panel && name !== except) panel.hidden = true;
    });
  }

  function lineDiff(before, after) {
    const a = String(before || '').split('\n');
    const b = String(after || '').split('\n');
    const cells = (a.length + 1) * (b.length + 1);
    if (cells > 90000) {
      return [{kind:'del', text:before}, {kind:'add', text:after}];
    }
    const dp = Array.from({length:a.length + 1}, () => new Uint16Array(b.length + 1));
    for (let i = a.length - 1; i >= 0; i--) {
      for (let j = b.length - 1; j >= 0; j--) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const out = [];
    let i = 0, j = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        out.push({kind:'same', text:a[i]}); i++; j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        out.push({kind:'del', text:a[i++]});
      } else {
        out.push({kind:'add', text:b[j++]});
      }
    }
    while (i < a.length) out.push({kind:'del', text:a[i++]});
    while (j < b.length) out.push({kind:'add', text:b[j++]});
    return out;
  }

  function renderDiff() {
    if (!diffBody || !diffPanel) return;
    const diff = lineDiff(originalText, currentText());
    const adds = diff.filter(row => row.kind === 'add').length;
    const dels = diff.filter(row => row.kind === 'del').length;
    const changed = adds + dels;
    const rows = changed
      ? diff.map(row => '<div class="script-diff-line ' + row.kind + '"><b>' + (row.kind === 'add' ? '+' : row.kind === 'del' ? '−' : ' ') + '</b><span>' + escapeHtml(row.text || ' ') + '</span></div>').join('')
      : '<p class="script-history-empty">El guion actual es idéntico al original.</p>';
    diffBody.innerHTML =
      '<div class="script-diff-summary"><span><strong>' + adds + '</strong> líneas añadidas</span><span><strong>' + dels + '</strong> líneas eliminadas</span><span>Δ ' + (wordCount(currentText()) - wordCount(originalText)) + ' palabras</span></div>' +
      '<div class="script-diff">' + rows + '</div>';
    closePanels('diff');
    diffPanel.hidden = !diffPanel.hidden;
  }

  function restoreHistoryVersion(item) {
    const stamp = new Date().toISOString();
    const record = {
      version: 1,
      episode: episodeKey,
      baseText: originalText,
      text: item.text,
      savedText: item.text,
      savedAt: stamp,
      draftAt: stamp,
      dirty: false,
    };
    try {
      localStorage.setItem(editorStorageKey, JSON.stringify(record));
      addHistorySnapshot(item.text, stamp, 'restore');
      window.location.reload();
    } catch (_) {
      scriptNode.textContent = item.text;
      document.dispatchEvent(new CustomEvent('reviewhub:script-content', {detail:item.text}));
      updateMetrics();
    }
  }

  function renderHistory() {
    if (!historyBody || !historyPanel) return;
    const history = readHistory();
    const saved = history.map((item, index) =>
      '<article class="script-history-item">' +
        '<div><h4>Versión ' + (index + 1) + (item.source === 'restore' ? ' · restaurada' : '') + '</h4>' +
        '<p>' + escapeHtml(fmt(item.savedAt)) + ' · ' + Number(item.words || wordCount(item.text)).toLocaleString('es-MX') + ' palabras · ~' + formatDuration(item.words || wordCount(item.text)) + '</p></div>' +
        '<button type="button" data-history-index="' + index + '">Restaurar</button>' +
      '</article>'
    ).join('');
    historyBody.innerHTML =
      '<div class="script-history-list">' +
      (saved || '<p class="script-history-empty">Todavía no hay versiones guardadas explícitamente.</p>') +
      '<article class="script-history-item script-history-original"><div><h4>Original del pipeline</h4><p>' + wordCount(originalText).toLocaleString('es-MX') + ' palabras · ~' + formatDuration(wordCount(originalText)) + '</p></div><button type="button" data-history-original="1">Ver original</button></article>' +
      '</div>';
    historyBody.querySelectorAll('[data-history-index]').forEach(button => {
      button.addEventListener('click', () => {
        const item = history[Number(button.dataset.historyIndex)];
        if (item && window.confirm('¿Restaurar esta versión como guion guardado actual?')) restoreHistoryVersion(item);
      });
    });
    historyBody.querySelector('[data-history-original]')?.addEventListener('click', () => {
      closePanels();
      if (diffBody && diffPanel) {
        diffBody.innerHTML = '<div class="script-diff"><div class="script-diff-line same"><b> </b><span>' + escapeHtml(originalText) + '</span></div></div>';
        diffPanel.hidden = false;
      }
    });
    closePanels('history');
    historyPanel.hidden = !historyPanel.hidden;
  }

  scriptNode.addEventListener('input', updateMetrics);
  document.addEventListener('reviewhub:script-content', updateMetrics);

  saveButton.addEventListener('click', () => {
    const record = readEditorRecord();
    if (record && typeof record.savedText === 'string') {
      addHistorySnapshot(record.savedText, record.savedAt || new Date().toISOString(), 'save');
    }
    updateMetrics();
  });

  restoreButton?.addEventListener('click', () => setTimeout(updateMetrics, 0));
  diffButton?.addEventListener('click', renderDiff);
  historyButton?.addEventListener('click', renderHistory);
  document.querySelectorAll('[data-close-script-tool]').forEach(button => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.dataset.closeScriptTool);
      if (target) target.hidden = true;
    });
  });

  seedCurrentSavedVersion();
  updateMetrics();
})();
</script>
"""


def _productivity_markup() -> str:
    return (
        '<div id="scriptLiveMetrics" class="script-live-metrics" aria-live="polite">'
        '<span><strong id="scriptLiveWords">0</strong> palabras</span>'
        '<span><strong id="scriptLiveDuration">~0:00</strong> duración</span>'
        '<span id="scriptLiveDelta">sin cambio</span>'
        '</div>'
        '<section id="scriptDiffPanel" class="script-tool-panel" hidden>'
        '<div class="script-tool-panel-head"><h3>Cambios contra el original</h3>'
        '<button type="button" aria-label="Cerrar comparación" data-close-script-tool="scriptDiffPanel">×</button></div>'
        '<div id="scriptDiffBody" class="script-tool-panel-body"></div></section>'
        '<section id="scriptHistoryPanel" class="script-tool-panel" hidden>'
        '<div class="script-tool-panel-head"><h3>Historial local · últimas 5 versiones</h3>'
        '<button type="button" aria-label="Cerrar historial" data-close-script-tool="scriptHistoryPanel">×</button></div>'
        '<div id="scriptHistoryBody" class="script-tool-panel-body"></div></section>'
    )


def apply_script_productivity(
    document: str,
    *,
    episode_key: str,
    original_text: str,
    words_per_second: float,
) -> str:
    if 'data-script-productivity-runtime="v1"' in document:
        return document

    download_button = '<button id="scriptDownloadButton" class="button secondary" type="button">Descargar .txt</button>'
    if download_button not in document:
        raise RuntimeError("Review Hub v13 could not find Script editor actions")
    document = document.replace(
        download_button,
        download_button
        + '<button id="scriptDiffButton" class="button secondary" type="button">Ver cambios</button>'
        + '<button id="scriptHistoryButton" class="button secondary" type="button">Historial</button>',
        1,
    )

    script_node = '<div id="scriptText" class="script" data-search-script>'
    if script_node not in document:
        raise RuntimeError("Review Hub v13 could not find Script node")
    document = document.replace(script_node, _productivity_markup() + script_node, 1)
    document = document.replace('</style>', SCRIPT_PRODUCTIVITY_CSS + '\n</style>', 1)

    runtime = (
        SCRIPT_PRODUCTIVITY_JS
        .replace("__EPISODE_KEY__", json.dumps(episode_key, ensure_ascii=False))
        .replace("__ORIGINAL_TEXT__", json.dumps(original_text, ensure_ascii=False))
        .replace("__WORDS_PER_SECOND__", json.dumps(float(words_per_second)))
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
    index_path = _build_site_v12(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
        pricing_path=pricing_path,
    )
    from pipeline.review_media_pool import inject_pool_panel
    original_text = (episode_dir / "script.txt").read_text(encoding="utf-8").strip()
    document = index_path.read_text(encoding="utf-8")
    document = apply_script_productivity(
        document,
        episode_key=episode_dir.name,
        original_text=original_text,
        words_per_second=CONFIG.words_per_second,
    )
    document = inject_pool_panel(document, media_dir)
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
