from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.review_hub_catalog import build_catalog, discover_episodes


class ReviewHubCatalogTests(unittest.TestCase):
    def _episode(
        self,
        root: Path,
        episode_id: str,
        *,
        title: str,
        run_id: str,
        cost: float | None,
        status: str = "SCRIPT_NOT_APPROVED",
    ) -> Path:
        episode = root / episode_id
        (episode / "artifacts").mkdir(parents=True)
        (episode / "downloads").mkdir(parents=True)
        (episode / "scripts").mkdir(parents=True)
        (episode / "index.html").write_text(f"<html><body>{episode_id}</body></html>", encoding="utf-8")
        (episode / "artifacts" / "episode_plan.json").write_text(
            json.dumps({"episode_title": title}), encoding="utf-8"
        )
        (episode / "artifacts" / "run_state.json").write_text(
            json.dumps({"status": status}), encoding="utf-8"
        )
        (episode / "scripts" / f"latest-{episode_id}-run-{run_id}.txt").write_text(
            "script", encoding="utf-8"
        )
        if cost is not None:
            (episode / "downloads" / "cost_snapshot.json").write_text(
                json.dumps({"totals": {"known_direct_cost_usd": cost}}), encoding="utf-8"
            )
        return episode

    def test_discovers_distinct_episode_sites_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "episodes"
            self._episode(root, "2026-08-18", title="Primer episodio", run_id="111", cost=0.08)
            self._episode(root, "2026-08-21", title="Segundo episodio", run_id="222", cost=0.12)
            ignored = root / "2026-08-22"
            ignored.mkdir(parents=True)

            episodes = discover_episodes(root)

            self.assertEqual([item["id"] for item in episodes], ["2026-08-21", "2026-08-18"])
            self.assertEqual(episodes[0]["run_id"], "222")
            self.assertEqual(episodes[0]["status"], "No aprobado")
            self.assertEqual(episodes[0]["known_direct_cost_usd"], 0.12)

    def test_build_catalog_adds_left_sidebar_and_query_driven_episode_switching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "episodes"
            output = base / "pages"
            self._episode(root, "2026-08-18", title="Primer episodio", run_id="111", cost=0.08)
            self._episode(root, "2026-08-21", title="Segundo episodio", run_id="222", cost=0.12)

            index = build_catalog(episodes_root=root, output_dir=output, current_id="2026-08-18")
            document = index.read_text(encoding="utf-8")
            manifest = json.loads((output / "episodes.json").read_text(encoding="utf-8"))

            self.assertIn('class="episode-sidebar"', document)
            self.assertIn('id="episodeFrame"', document)
            self.assertIn('id="episodeSearch"', document)
            self.assertIn('placeholder="Buscar episodio…"', document)
            self.assertIn("URLSearchParams(window.location.search).get('episode')", document)
            self.assertIn("history.pushState", document)
            self.assertIn('src="episodes/2026-08-18/index.html"', document)
            self.assertIn('data-episode-id="2026-08-21"', document)
            self.assertIn('data-episode-id="2026-08-18"', document)
            self.assertEqual(manifest["default_episode"], "2026-08-18")
            self.assertEqual(len(manifest["episodes"]), 2)

    def test_unknown_current_episode_falls_back_to_newest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "episodes"
            output = base / "pages"
            self._episode(root, "2026-08-18", title="Viejo", run_id="111", cost=None)
            self._episode(root, "2026-08-21", title="Nuevo", run_id="222", cost=None)

            build_catalog(episodes_root=root, output_dir=output, current_id="2099-01-01")
            manifest = json.loads((output / "episodes.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["default_episode"], "2026-08-21")

    def test_empty_catalog_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaises(RuntimeError):
                build_catalog(
                    episodes_root=base / "episodes",
                    output_dir=base / "pages",
                    current_id=None,
                )


if __name__ == "__main__":
    unittest.main()
