from __future__ import annotations

import unittest

from pipeline.review_hub_v12 import apply_script_editor
from pipeline.review_hub_v13 import apply_script_productivity


class ScriptProductivityTests(unittest.TestCase):
    def _base_document(self) -> str:
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

    def _editor_document(self) -> str:
        return apply_script_editor(self._base_document(), episode_key="2026-09-24")

    def test_injects_metrics_diff_and_history_controls(self) -> None:
        rendered = apply_script_productivity(
            self._editor_document(),
            episode_key="2026-09-24",
            original_text="Texto original",
            words_per_second=2.5,
        )
        self.assertIn('id="scriptLiveWords"', rendered)
        self.assertIn('id="scriptLiveDuration"', rendered)
        self.assertIn('id="scriptDiffButton"', rendered)
        self.assertIn('id="scriptHistoryButton"', rendered)
        self.assertIn('id="scriptDiffPanel"', rendered)
        self.assertIn('id="scriptHistoryPanel"', rendered)
        self.assertIn('data-script-productivity-runtime="v1"', rendered)

    def test_history_is_bounded_and_episode_scoped(self) -> None:
        rendered = apply_script_productivity(
            self._editor_document(),
            episode_key="2026-09-24",
            original_text="Texto original",
            words_per_second=2.5,
        )
        self.assertIn("const MAX_HISTORY = 5;", rendered)
        self.assertIn("ai-news-daily:script-history:v1:", rendered)
        self.assertIn('"2026-09-24"', rendered)

    def test_uses_configured_reading_speed(self) -> None:
        rendered = apply_script_productivity(
            self._editor_document(),
            episode_key="2026-09-24",
            original_text="uno dos tres cuatro cinco",
            words_per_second=2.75,
        )
        self.assertIn("const wordsPerSecond = 2.75;", rendered)

    def test_productivity_layer_is_idempotent(self) -> None:
        once = apply_script_productivity(
            self._editor_document(),
            episode_key="2026-09-24",
            original_text="Texto original",
            words_per_second=2.5,
        )
        twice = apply_script_productivity(
            once,
            episode_key="2026-09-24",
            original_text="Texto original",
            words_per_second=2.5,
        )
        self.assertEqual(once, twice)
        self.assertEqual(once.count('data-script-productivity-runtime="v1"'), 1)

    def test_requires_existing_editor(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "could not find Script editor actions"):
            apply_script_productivity(
                self._base_document(),
                episode_key="2026-09-24",
                original_text="Texto original",
                words_per_second=2.5,
            )


if __name__ == "__main__":
    unittest.main()
