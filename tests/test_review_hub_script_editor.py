from __future__ import annotations

import unittest

from pipeline.review_hub_v12 import apply_script_editor


class ScriptEditorTests(unittest.TestCase):
    def _document(self) -> str:
        return """<!doctype html>
<html>
<head><style>.script{white-space:pre-wrap}</style></head>
<body>
<section id="guion" data-search-group><h2>Guion actual</h2><div id="scriptText" class="script" data-search-script>Texto original</div></section>
<script>
(() => {
  const scriptNode = document.getElementById('scriptText');
  const norm = value => String(value || '').toLowerCase();
  const scriptOriginal = scriptNode.textContent;
  const normalizedScript = norm(scriptOriginal);
})();
</script>
</body>
</html>"""

    def test_injects_edit_save_restore_and_download_controls(self) -> None:
        rendered = apply_script_editor(self._document(), episode_key="2026-09-24")
        self.assertIn('data-script-editor="v1"', rendered)
        self.assertIn('id="scriptEditButton"', rendered)
        self.assertIn('id="scriptSaveButton"', rendered)
        self.assertIn('id="scriptRestoreButton"', rendered)
        self.assertIn('id="scriptDownloadButton"', rendered)
        self.assertIn("ai-news-daily:script-editor:v1:", rendered)
        self.assertIn('"2026-09-24"', rendered)

    def test_search_state_becomes_refreshable_after_edits(self) -> None:
        rendered = apply_script_editor(self._document(), episode_key="2026-09-24")
        self.assertIn("let scriptOriginal = scriptNode.textContent;", rendered)
        self.assertIn("let normalizedScript = norm(scriptOriginal);", rendered)
        self.assertIn("reviewhub:script-content", rendered)
        self.assertNotIn("const scriptOriginal = scriptNode.textContent;", rendered)
        self.assertNotIn("const normalizedScript = norm(scriptOriginal);", rendered)

    def test_editor_is_idempotent(self) -> None:
        once = apply_script_editor(self._document(), episode_key="2026-09-24")
        twice = apply_script_editor(once, episode_key="2026-09-24")
        self.assertEqual(once, twice)
        self.assertEqual(once.count('data-script-editor="v1"'), 1)

    def test_requires_expected_script_contract(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "could not find Script section"):
            apply_script_editor("<html><style></style><body></body></html>", episode_key="2026-09-24")


if __name__ == "__main__":
    unittest.main()
