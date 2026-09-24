from __future__ import annotations

import html
import json
from pathlib import Path

from pipeline.review_hub_v3 import parse_args
from pipeline.review_hub_v11 import build_site as _build_site_v11


SCRIPT_EDITOR_CSS = r"""
/* v12: lightweight, browser-local script editing without a backend. */
.script-editor-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 auto 12px;max-width:850px;padding:10px 12px;border:1px solid var(--line);border-radius:13px;background:#101824}
.script-editor-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.script-editor-toolbar .button{margin:0;cursor:pointer}.script-editor-toolbar .button.primary{background:#17344a;border-color:#356789;color:#dff5ff}.script-editor-status{color:var(--muted);font-size:11px;line-height:1.35}.script-editor-status strong{color:#dce9f5}.script-editor-status.dirty{color:#ffd38a}.script-editor-status.saved{color:#9ee6bd}.script-editor-status.warn{color:#ffb8c4}
#scriptText[contenteditable="true"],#scriptText[contenteditable="plaintext-only"]{outline:0;border-color:#47779c;box-shadow:0 0 0 3px #7dd3fc18;background:#0d1520;caret-color:#dff5ff}
#scriptText.script-editing{min-height:420px}.script-editor-hint{width:100%;margin:0;color:#8294a7;font-size:10px}
@media(max-width:760px){.script-editor-toolbar{max-width:none;align-items:stretch}.script-editor-actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));width:100%}.script-editor-toolbar .button{width:100%;min-height:42px}.script-editor-status{width:100%}}
"""


SCRIPT_EDITOR_JS_TEMPLATE = r"""
<script data-script-editor-runtime="v1">
(() => {
  const scriptNode = document.getElementById('scriptText');
  const editButton = document.getElementById('scriptEditButton');
  const saveButton = document.getElementById('scriptSaveButton');
  const cancelButton = document.getElementById('scriptCancelButton');
  const restoreButton = document.getElementById('scriptRestoreButton');
  const downloadButton = document.getElementById('scriptDownloadButton');
  const statusNode = document.getElementById('scriptEditorStatus');
  if (!scriptNode || !editButton || !saveButton || !cancelButton || !restoreButton || !statusNode) return;

  const episodeKey = __EPISODE_KEY__;
  const storageKey = 'ai-news-daily:script-editor:v1:' + episodeKey;
  const originalText = scriptNode.textContent;
  let record = null;
  let editing = false;
  let draftTimer = null;
  let storageAvailable = true;

  const nowIso = () => new Date().toISOString();
  const fmt = value => {
    if (!value) return '';
    try { return new Intl.DateTimeFormat('es-MX', {dateStyle:'medium', timeStyle:'short'}).format(new Date(value)); }
    catch (_) { return value; }
  };
  const text = () => scriptNode.textContent || '';

  function readRecord() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (_) {
      storageAvailable = false;
      return null;
    }
  }

  function writeRecord(next) {
    record = next;
    if (!storageAvailable) return false;
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
      return true;
    } catch (_) {
      storageAvailable = false;
      return false;
    }
  }

  function removeRecord() {
    record = null;
    if (!storageAvailable) return;
    try { localStorage.removeItem(storageKey); }
    catch (_) { storageAvailable = false; }
  }

  function publishScriptState(value) {
    document.dispatchEvent(new CustomEvent('reviewhub:script-content', {detail:String(value || '')}));
  }

  function setStatus(message, kind='') {
    statusNode.className = 'script-editor-status' + (kind ? ' ' + kind : '');
    statusNode.innerHTML = message;
  }

  function setScript(value) {
    scriptNode.textContent = String(value || '');
    publishScriptState(scriptNode.textContent);
  }

  function latestSavedText() {
    if (record && typeof record.savedText === 'string') return record.savedText;
    return originalText;
  }

  function updateControls() {
    editButton.hidden = editing;
    saveButton.hidden = !editing;
    cancelButton.hidden = !editing;
    restoreButton.disabled = editing;
    if (downloadButton) downloadButton.disabled = editing;
  }

  function enterEdit() {
    editing = true;
    scriptNode.setAttribute('contenteditable', 'plaintext-only');
    scriptNode.setAttribute('spellcheck', 'true');
    scriptNode.classList.add('script-editing');
    updateControls();
    setStatus('Editando · los cambios se recuperan como borrador aunque salgas de la página.', 'dirty');
    scriptNode.focus();
  }

  function exitEdit() {
    editing = false;
    scriptNode.removeAttribute('contenteditable');
    scriptNode.removeAttribute('spellcheck');
    scriptNode.classList.remove('script-editing');
    updateControls();
  }

  function persistDraft() {
    const value = text();
    const savedText = record && typeof record.savedText === 'string' ? record.savedText : originalText;
    const savedAt = record && record.savedAt ? record.savedAt : null;
    const next = {
      version: 1,
      episode: episodeKey,
      baseText: originalText,
      text: value,
      savedText,
      savedAt,
      draftAt: nowIso(),
      dirty: value !== savedText,
    };
    const ok = writeRecord(next);
    if (!ok) {
      setStatus('No pude escribir en el almacenamiento del navegador. Usa “Descargar .txt” antes de salir.', 'warn');
      return;
    }
    if (next.dirty) setStatus('Borrador recuperable guardado automáticamente · pulsa <strong>Guardar</strong> para confirmar.', 'dirty');
  }

  function save() {
    if (draftTimer) {
      clearTimeout(draftTimer);
      draftTimer = null;
    }
    const value = text();
    const stamp = nowIso();
    const ok = writeRecord({
      version: 1,
      episode: episodeKey,
      baseText: originalText,
      text: value,
      savedText: value,
      savedAt: stamp,
      draftAt: stamp,
      dirty: false,
    });
    publishScriptState(value);
    exitEdit();
    setStatus(ok ? ('Guardado en este navegador · <strong>' + fmt(stamp) + '</strong>') : 'Edición aplicada en esta sesión, pero el navegador bloqueó la persistencia.', ok ? 'saved' : 'warn');
  }

  function cancel() {
    if (draftTimer) {
      clearTimeout(draftTimer);
      draftTimer = null;
    }
    const value = latestSavedText();
    setScript(value);
    if (record) {
      record.text = value;
      record.dirty = false;
      record.draftAt = nowIso();
      writeRecord(record);
    }
    exitEdit();
    setStatus(record && record.savedAt ? ('Cambios descartados · versión guardada de <strong>' + fmt(record.savedAt) + '</strong>') : 'Cambios descartados · mostrando la versión original.', '');
  }

  function restoreOriginal() {
    if (!window.confirm('¿Restaurar el guion original de este episodio y eliminar la copia local guardada?')) return;
    removeRecord();
    setScript(originalText);
    exitEdit();
    setStatus('Versión original restaurada · no hay edición local guardada.', '');
  }

  function downloadCurrent() {
    const blob = new Blob([text() + '\n'], {type:'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'script-' + episodeKey + '-editado.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  editButton.addEventListener('click', enterEdit);
  saveButton.addEventListener('click', save);
  cancelButton.addEventListener('click', cancel);
  restoreButton.addEventListener('click', restoreOriginal);
  if (downloadButton) downloadButton.addEventListener('click', downloadCurrent);

  scriptNode.addEventListener('input', () => {
    if (!editing) return;
    if (draftTimer) clearTimeout(draftTimer);
    draftTimer = setTimeout(persistDraft, 250);
  });

  scriptNode.addEventListener('paste', event => {
    if (!editing) return;
    const plain = event.clipboardData && event.clipboardData.getData('text/plain');
    if (plain == null) return;
    event.preventDefault();
    document.execCommand('insertText', false, plain);
  });

  document.addEventListener('keydown', event => {
    if (!editing) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      save();
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      cancel();
    }
  });

  record = readRecord();
  if (record && typeof record.text === 'string') {
    setScript(record.text);
    const baseChanged = typeof record.baseText === 'string' && record.baseText !== originalText;
    if (record.dirty) {
      setStatus((baseChanged ? 'El guion base cambió desde tu edición. ' : '') + 'Borrador recuperado · <strong>' + fmt(record.draftAt) + '</strong>', baseChanged ? 'warn' : 'dirty');
    } else if (record.savedAt) {
      setStatus((baseChanged ? 'El guion base cambió desde tu edición. ' : '') + 'Versión local guardada · <strong>' + fmt(record.savedAt) + '</strong>', baseChanged ? 'warn' : 'saved');
    }
  } else {
    setStatus(storageAvailable ? 'Versión original · todavía no hay edición local guardada.' : 'El navegador bloqueó el almacenamiento local; puedes editar y descargar el TXT.', storageAvailable ? '' : 'warn');
  }
  updateControls();
})();
</script>
"""


def _editor_toolbar() -> str:
    return (
        '<div class="script-editor-toolbar" data-script-editor="v1">'
        '<div class="script-editor-actions">'
        '<button id="scriptEditButton" class="button primary" type="button">Editar</button>'
        '<button id="scriptSaveButton" class="button primary" type="button" hidden>Guardar</button>'
        '<button id="scriptCancelButton" class="button secondary" type="button" hidden>Cancelar</button>'
        '<button id="scriptRestoreButton" class="button secondary" type="button">Restaurar original</button>'
        '<button id="scriptDownloadButton" class="button secondary" type="button">Descargar .txt</button>'
        '</div>'
        '<span id="scriptEditorStatus" class="script-editor-status" role="status" aria-live="polite"></span>'
        '<p class="script-editor-hint">La edición se guarda por episodio en este navegador y sobrevive al cerrar o volver a abrir Pages. No modifica el artefacto fuente del pipeline.</p>'
        '</div>'
    )


def apply_script_editor(document: str, *, episode_key: str) -> str:
    if 'data-script-editor="v1"' in document:
        return document

    needle = '<section id="guion" data-search-group><h2>Guion actual</h2><div id="scriptText" class="script" data-search-script>'
    if needle not in document:
        raise RuntimeError("Review Hub v12 could not find Script section")

    replacement = (
        '<section id="guion" data-search-group><h2>Guion actual</h2>'
        + _editor_toolbar()
        + '<div id="scriptText" class="script" data-search-script>'
    )
    document = document.replace(needle, replacement, 1)
    document = document.replace('</style>', SCRIPT_EDITOR_CSS + '\n</style>', 1)

    # The original global search closure captured the generated script once. Make that
    # state refreshable so searching after an edit never resurrects stale text.
    original_decl = "  const scriptOriginal = scriptNode.textContent;"
    normalized_decl = "  const normalizedScript = norm(scriptOriginal);"
    if original_decl not in document or normalized_decl not in document:
        raise RuntimeError("Review Hub v12 could not patch Script search state")
    document = document.replace(original_decl, "  let scriptOriginal = scriptNode.textContent;", 1)
    document = document.replace(
        normalized_decl,
        "  let normalizedScript = norm(scriptOriginal);\n"
        "  document.addEventListener('reviewhub:script-content', event => {\n"
        "    scriptOriginal = String(event.detail || '');\n"
        "    normalizedScript = norm(scriptOriginal);\n"
        "  });",
        1,
    )

    runtime = SCRIPT_EDITOR_JS_TEMPLATE.replace("__EPISODE_KEY__", json.dumps(episode_key, ensure_ascii=False))
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
    index_path = _build_site_v11(
        episode_dir=episode_dir,
        media_dir=media_dir,
        media_zip=media_zip,
        regression_path=regression_path,
        cases_path=cases_path,
        output_dir=output_dir,
        run_id=run_id,
        pricing_path=pricing_path,
    )
    episode_key = html.escape(episode_dir.name, quote=True)
    document = index_path.read_text(encoding="utf-8")
    document = apply_script_editor(document, episode_key=episode_key)
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
