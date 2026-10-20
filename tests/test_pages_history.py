from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.pages_history import (
    ArtifactMeta,
    discover_catalog_roots,
    discover_episode_sites,
    merge_catalog_snapshot,
    rank_artifacts,
    recover_history,
)


EPISODE_HTML = '''<!doctype html><html><body>
<div id="globalSearch"></div><button data-tab="overview"></button>
<p>{date}</p></body></html>'''
CATALOG_HTML = '''<!doctype html><html><body>
<nav class="episode-sidebar"></nav><iframe id="episodeFrame"></iframe>
</body></html>'''


class PagesHistoryTests(unittest.TestCase):
    def _episode_site(self, root: Path, date_value: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "artifacts").mkdir(exist_ok=True)
        (root / "artifacts" / "run_state.json").write_text(
            json.dumps({"status": "SCRIPT_NOT_APPROVED"}), encoding="utf-8"
        )
        (root / "index.html").write_text(
            EPISODE_HTML.format(date=date_value), encoding="utf-8"
        )
        return root

    def test_design_preview_is_excluded_even_with_renamed_artifact_and_complete_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = self._snapshot(root / "renamed" / "nested", ["2026-09-04"])
            (preview / "preview-provenance.json").write_text('{}')
            self.assertEqual(discover_catalog_roots(root), [])
            self.assertEqual(discover_episode_sites(root), [])
            output = root / "output"
            self.assertEqual(merge_catalog_snapshot(preview, output, set(), 8), 0)
            self.assertFalse(output.exists())

    def test_incomplete_snapshot_does_not_hide_older_complete_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contaminated = self._snapshot(root / "recent", ["2026-09-04"])
            incomplete = contaminated / "episodes" / "2026-09-04"
            (incomplete / "artifacts" / "run_state.json").unlink()
            # A badge is presentation, not persisted approval authority.
            (incomplete / "index.html").write_text(EPISODE_HTML.format(date="2026-09-04") + '<span>APPROVED</span>')
            complete = self._snapshot(root / "older", ["2026-09-04"])
            source = complete / "episodes" / "2026-09-04"
            (source / "media").mkdir()
            (source / "media" / "image.jpg").write_bytes(b'original-media')
            (source / "downloads").mkdir()
            (source / "downloads" / "cost_snapshot.json").write_text('{"totals":{"known_direct_cost_usd":0.126}}')
            seen = {"2026-09-25"}
            output = root / "output"
            self.assertEqual(merge_catalog_snapshot(contaminated, output, seen, 8), 0)
            self.assertNotIn("2026-09-04", seen)
            self.assertEqual(merge_catalog_snapshot(complete, output, seen, 8), 1)
            recovered = output / "episodes" / "2026-09-04"
            self.assertEqual((recovered / "media" / "image.jpg").read_bytes(), b'original-media')
            from pipeline.review_hub_catalog import episode_metadata
            metadata = episode_metadata(recovered)
            self.assertEqual(metadata['status'], 'No aprobado')
            self.assertEqual(metadata['known_direct_cost_usd'], .126)

    def test_standalone_html_without_state_is_not_a_recovery_source(self) -> None:
        from pipeline.pages_history import merge_episode_site
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = self._episode_site(root / 'site', '2026-09-04')
            state = site / 'artifacts' / 'run_state.json'
            output = root / 'output'
            for invalid in ('null', '[]', '{invalid', '{}', '{"status":""}'):
                state.write_text(invalid)
                self.assertFalse(merge_episode_site('2026-09-04', site, output, set(), 8))
            state.unlink()
            (site / 'artifacts' / 'reviews.json').write_text('{"approved":false}')
            self.assertTrue(merge_episode_site('2026-09-04', site, output, set(), 8))

    def _snapshot(self, root: Path, dates: list[str]) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text(CATALOG_HTML, encoding="utf-8")
        (root / "episodes.json").write_text(json.dumps(dates), encoding="utf-8")
        for value in dates:
            self._episode_site(root / "episodes" / value, value)
        return root

    def test_catalog_discovery_uses_structure_not_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._snapshot(root / "arbitrary/deep/name", ["2026-09-01"])
            self.assertEqual(discover_catalog_roots(root), [expected])

    def test_episode_discovery_uses_html_contract_not_artifact_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._episode_site(root / "whatever/site", "2026-09-04")
            found = discover_episode_sites(root, "totally-random-artifact")
            self.assertEqual(found, [("2026-09-04", expected)])

    def test_snapshot_merges_multiple_distinct_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(
                root / "snapshot", ["2026-09-04", "2026-09-01", "2026-08-29"]
            )
            output = root / "pages"
            (output / "episodes").mkdir(parents=True)
            seen = {"2026-09-05"}
            added = merge_catalog_snapshot(snapshot, output, seen, limit=3)
            self.assertEqual(added, 2)
            self.assertEqual(len(seen), 3)

    def test_historical_episode_video_preview_is_lazy_and_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(root / "snapshot", ["2026-09-04"])
            episode_index = snapshot / "episodes" / "2026-09-04" / "index.html"
            document = episode_index.read_text(encoding="utf-8").replace(
                "</body>",
                "<article class='media-card'><video controls preload='none'><source src='media/clip.mp4' type='video/mp4'></video></article></body>",
            )
            episode_index.write_text(document, encoding="utf-8")

            output = root / "pages"
            (output / "episodes").mkdir(parents=True)
            seen = {"2026-09-05"}
            added = merge_catalog_snapshot(snapshot, output, seen, limit=2)

            self.assertEqual(added, 1)
            recovered = (output / "episodes" / "2026-09-04" / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertIn('data-lazy-video-preview="v1"', recovered)
            self.assertIn("MAX_CONCURRENT_PREVIEWS = 2", recovered)
            self.assertIn("IntersectionObserver", recovered)

    def test_artifact_rank_prefers_lightweight_review_hint_but_names_are_not_required(self) -> None:
        artifacts = [
            ArtifactMeta(1, "random-heavy", 1, 200_000_000, "2026-09-06T10:00:00Z"),
            ArtifactMeta(2, "anything", 2, 2_000_000, "2026-09-06T09:00:00Z"),
            ArtifactMeta(3, "pages-snapshot", 3, 5_000_000, "2026-09-06T08:00:00Z"),
        ]
        ranked = rank_artifacts(artifacts)
        self.assertEqual(ranked[0].name, "pages-snapshot")
        self.assertIn("anything", [item.name for item in ranked])

    def test_known_design_preview_does_not_consume_recovery_candidate_budget(self) -> None:
        preview = ArtifactMeta(1, 'pages-design-preview', 1, 1024, '2026-10-20T01:14:38Z')
        real = ArtifactMeta(2, 'editorial-pages-snapshot', 2, 200_000_000, '2026-10-19T23:36:34Z')
        self.assertEqual(rank_artifacts([preview, real]), [real])

    def test_recover_history_accepts_renamed_snapshot_by_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = self._episode_site(root / "current", "2026-09-05")
            extracted = root / "downloaded"
            self._snapshot(extracted / "mystery-folder", ["2026-09-04", "2026-09-01"])
            payload = {
                "artifacts": [
                    {
                        "id": 10,
                        "name": "completely-renamed",
                        "size_in_bytes": 1024,
                        "created_at": "2026-09-06T10:00:00Z",
                        "expired": False,
                        "workflow_run": {"id": 99},
                    }
                ]
            }

            def fake_download(meta, destination):
                import shutil
                shutil.copytree(extracted, destination, dirs_exist_ok=True)
                return True

            with patch("pipeline.pages_history._download_artifact", side_effect=fake_download):
                report = recover_history(
                    repository="owner/repo",
                    current_site=current,
                    current_date="2026-09-05",
                    output_root=root / "pages",
                    history_limit=3,
                    artifact_payload=payload,
                )
            self.assertEqual(report["episode_count"], 3)
            self.assertEqual(
                set(report["episode_dates"]),
                {"2026-09-05", "2026-09-04", "2026-09-01"},
            )

    def test_recovery_passes_previews_and_incomplete_snapshots_to_restore_real_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = self._episode_site(root / 'current', '2026-09-25')
            preview = self._snapshot(root / 'preview', ['2026-10-16'])
            (preview / 'preview-provenance.json').write_text('{}')
            contaminated = self._snapshot(root / 'incomplete', ['2026-10-16'])
            (contaminated / 'episodes/2026-10-16/artifacts/run_state.json').unlink()
            real = self._snapshot(root / 'real', ['2026-10-16'])
            sources = {1: preview, 2: contaminated, 3: real}
            payload = {'artifacts': [
                dict(id=i, name='renamed-pages-site', size_in_bytes=1024,
                     created_at=f'2026-10-{21-i:02d}T00:00:00Z', workflow_run={'id': i})
                for i in sources
            ]}
            def download(meta, destination):
                import shutil
                shutil.copytree(sources[meta.artifact_id], destination)
                return True
            with patch('pipeline.pages_history._download_artifact', side_effect=download):
                report = recover_history(repository='owner/repo', current_site=current,
                    current_date='2026-09-25', output_root=root / 'output',
                    history_limit=2, artifact_payload=payload)
            self.assertEqual(report['candidates_considered'], 3)
            self.assertEqual(report['episode_count'], 2)
            from pipeline.review_hub_catalog import discover_episodes
            episodes = discover_episodes(root / 'output/episodes')
            self.assertEqual(episodes[0]['id'], '2026-10-16')
            self.assertEqual(episodes[0]['status'], 'No aprobado')

    def test_small_audits_do_not_consume_large_snapshot_download_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = self._episode_site(root / 'current', '2026-09-25')
            real = self._snapshot(root / 'real', ['2026-10-16'])
            artifacts = [dict(id=i, name='pages-cost-audit', size_in_bytes=1024,
                created_at=f'2026-10-{30-i:02d}T00:00:00Z', workflow_run={'id': i}) for i in range(1, 10)]
            artifacts.append(dict(id=10, name='editorial-pages-snapshot', size_in_bytes=200_000_000,
                created_at='2026-10-01T00:00:00Z', workflow_run={'id': 10}))
            downloaded = []
            def download(meta, destination):
                import shutil
                downloaded.append(meta.artifact_id)
                destination.mkdir(parents=True)
                if meta.artifact_id == 10:shutil.copytree(real, destination, dirs_exist_ok=True)
                return True
            with patch('pipeline.pages_history._download_artifact', side_effect=download):
                report = recover_history(repository='owner/repo', current_site=current,
                    current_date='2026-09-25', output_root=root / 'output', history_limit=2,
                    artifact_payload={'artifacts': artifacts})
            self.assertIn(10, downloaded)
            self.assertEqual(report['episode_count'], 2)

    def test_large_artifact_attempts_remain_bounded_to_eight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = self._episode_site(root / 'current', '2026-09-25')
            artifacts = [dict(id=i, name='editorial-pages-snapshot', size_in_bytes=200_000_000,
                created_at=f'2026-10-{30-i:02d}T00:00:00Z', workflow_run={'id': i}) for i in range(1, 11)]
            with patch('pipeline.pages_history._download_artifact', return_value=False) as download:
                report = recover_history(repository='owner/repo', current_site=current,
                    current_date='2026-09-25', output_root=root / 'output', history_limit=2,
                    artifact_payload={'artifacts': artifacts})
            self.assertEqual(download.call_count, 8)
            self.assertEqual(sum(d['status']=='skipped_too_large' for d in report['diagnostics']), 2)

    def test_missing_known_historical_date_blocks_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = self._episode_site(root / 'current', '2026-09-25')
            incomplete = self._snapshot(root / 'incomplete', ['2026-10-16'])
            (incomplete / 'episodes/2026-10-16/artifacts/run_state.json').unlink()
            artifact = dict(id=1, name='editorial-pages-snapshot', size_in_bytes=1024,
                created_at='2026-10-20T00:00:00Z', workflow_run={'id': 1})
            def download(meta, destination):
                import shutil
                shutil.copytree(incomplete, destination)
                return True
            with patch('pipeline.pages_history._download_artifact', side_effect=download):
                with self.assertRaisesRegex(RuntimeError, 'refusing publication.*2026-10-16'):
                    recover_history(repository='owner/repo', current_site=current,
                        current_date='2026-09-25', output_root=root / 'output', history_limit=8,
                        artifact_payload={'artifacts': [artifact]})


if __name__ == "__main__":
    unittest.main()
