from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.repo_health import audit_repository, health_document, write_health_outputs


class RepoHealthTests(unittest.TestCase):
    def _bootstrap(self, root: Path) -> None:
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "news").mkdir()
        (root / "scripts").mkdir()
        (root / "README.md").write_text("# repo\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
        (root / "requirements.lock").write_text("requests==2.34.2\n", encoding="utf-8")
        (root / ".gitignore").write_text(".env\n.pipeline-runs/\n", encoding="utf-8")
        (root / ".github" / "dependabot.yml").write_text(
            "version: 2\nupdates: []\n", encoding="utf-8"
        )
        (root / "pyproject.toml").write_text(
            '[project]\nrequires-python = ">=3.11"\n',
            encoding="utf-8",
        )
        workflows = {
            "ci.yml": """name: CI
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@0123456789012345678901234567890123456789
      - uses: actions/setup-python@0123456789012345678901234567890123456789
        with:
          python-version: "3.11"
""",
            "build-video-kit.yml": "name: Build AI News Video Kit\n",
            "ingest-news-staging.yml": "name: Ingest AI News Staging\n",
            "production-preflight.yml": "name: Production Preflight\n",
            "news-ingestion-watchdog.yml": "name: News Ingestion Watchdog\n",
            "editorial-regression.yml": """name: Editorial Regression
run-name: regression
""",
            "editorial-review-hub.yml": "name: Editorial Review Hub\n",
        }
        for name, text in workflows.items():
            (root / ".github" / "workflows" / name).write_text(text, encoding="utf-8")

    def _approved_episode(self, root: Path, value: str) -> None:
        episode = root / "scripts" / value
        episode.mkdir(parents=True)
        (episode / "run_state.json").write_text(
            json.dumps({"status": "approved", "publishable": True}),
            encoding="utf-8",
        )

    def _news(self, root: Path, filename: str, value: str) -> None:
        (root / "news" / filename).write_text(
            (
                "Título: Noticia de prueba\n"
                f"Fecha: {value}\n"
                "Fuente: Test\n"
                "Enlace: https://example.com/noticia\n"
                "Resumen breve: Resumen estructurado para validar cobertura.\n"
                "Por qué importa: Evidencia de prueba para el contrato.\n"
                "Categoría: prueba\n"
            ),
            encoding="utf-8",
        )

    def _pages(self, root: Path, value: str) -> Path:
        pages = root / "pages"
        (pages / "episodes" / value).mkdir(parents=True)
        (pages / "episodes" / value / "index.html").write_text(
            "<html></html>", encoding="utf-8"
        )
        (pages / "index.html").write_text("<html></html>", encoding="utf-8")
        return pages

    def _github(self) -> dict:
        successful = []
        for index, name in enumerate(
            ("CI", "Ingest AI News Staging", "News Ingestion Watchdog", "Production Preflight", "Build AI News Video Kit", "Editorial Regression", "Editorial Review Hub"),
            start=1,
        ):
            successful.append(
                {
                    "id": index,
                    "name": name,
                    "conclusion": "success",
                    "updated_at": "2026-09-24T12:00:00Z",
                }
            )
        return {
            "repository": {"size": 4096},
            "pulls": [],
            "issues": [],
            "workflow_runs": successful,
        }

    def test_reconcile_noop_success_does_not_mask_failed_pages_publication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            github = self._github()
            for run in github["workflow_runs"]:
                if run["name"] == "Editorial Review Hub":
                    run["conclusion"] = "failure"
            github["workflow_runs"].insert(0, {
                "id": 999, "name": "Drive reconciliation acknowledged (no Pages build)",
                "conclusion": "success", "updated_at": "2026-09-24T12:01:00Z",
            })
            report = audit_repository(repo_root=root, as_of=date(2026, 9, 24),
                                      github_snapshot=github, current_workflow_context={})
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual(checks["workflow-editorial-review-hub"]["status"], "critical")
            self.assertIn("failure", checks["workflow-editorial-review-hub"]["summary"])

    def test_clean_fixture_is_healthy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            for value in ("2026-09-22", "2026-09-23", "2026-09-24"):
                self._news(root, f"{value}-08-00-00.txt", value)
            self._approved_episode(root, "2026-09-22")
            pages = self._pages(root, "2026-09-22")

            report = audit_repository(
                repo_root=root,
                pages_root=pages,
                as_of=date(2026, 9, 24),
                github_snapshot=self._github(),
            )

            self.assertEqual(report["status"], "healthy")
            self.assertEqual(report["status_counts"]["critical"], 0)
            self.assertEqual(report["status_counts"]["warn"], 0)
            self.assertEqual(report["metrics"]["latest_news_date"], "2026-09-24")
            self.assertEqual(report["metrics"]["latest_episode_date"], "2026-09-22")

    def test_next_scheduled_run_readiness_detects_missing_source_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            self._news(root, "2026-09-24-12-42-52.txt", "2026-09-24")
            self._approved_episode(root, "2026-09-22")

            report = audit_repository(
                repo_root=root,
                as_of=date(2026, 9, 24),
                github_snapshot=self._github(),
            )
            checks = {item["id"]: item for item in report["checks"]}

            self.assertEqual(checks["next-run-readiness"]["status"], "critical")
            self.assertEqual(report["metrics"]["next_production_date"], "2026-09-25")
            self.assertAlmostEqual(report["metrics"]["next_source_coverage_ratio"], 1 / 3, places=4)
            self.assertEqual(
                report["metrics"]["next_source_missing_dates"],
                ["2026-09-22", "2026-09-23"],
            )

    def test_duplicate_sources_and_stale_production_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            for stamp in ("12-42-52", "12-43-40"):
                self._news(root, f"2026-09-24-{stamp}.txt", "2026-09-24")
            self._approved_episode(root, "2026-09-04")
            pages = self._pages(root, "2026-09-04")

            report = audit_repository(
                repo_root=root,
                pages_root=pages,
                as_of=date(2026, 9, 24),
                github_snapshot=self._github(),
            )
            checks = {item["id"]: item for item in report["checks"]}

            self.assertEqual(report["status"], "critical")
            self.assertEqual(checks["duplicate-news-days"]["status"], "warn")
            self.assertEqual(checks["production-freshness"]["status"], "critical")
            self.assertEqual(report["metrics"]["duplicate_news_days"]["2026-09-24"], [
                "2026-09-24-12-42-52.txt",
                "2026-09-24-12-43-40.txt",
            ])
            self.assertEqual(report["metrics"]["production_staleness_days"], 20)

    def test_detects_canonical_only_editorial_regression_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            workflow = root / ".github" / "workflows" / "editorial-regression.yml"
            workflow.write_text(
                """name: Editorial Regression
steps:
  - run: find news -maxdepth 1 -type f -name '????-??-??.txt' | sort | tail -1
""",
                encoding="utf-8",
            )
            self._news(root, "2026-09-24-12-42-52.txt", "2026-09-24")
            self._approved_episode(root, "2026-09-22")

            report = audit_repository(
                repo_root=root,
                as_of=date(2026, 9, 24),
                github_snapshot=self._github(),
            )
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual(checks["regression-source-contract"]["status"], "warn")
            self.assertIn("timestamped", checks["regression-source-contract"]["detail"])

    def test_detects_declared_python_311_but_ci_only_312(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            ci = root / ".github" / "workflows" / "ci.yml"
            ci.write_text(
                """name: CI
jobs:
  tests:
    steps:
      - uses: actions/checkout@0123456789012345678901234567890123456789
      - uses: actions/setup-python@0123456789012345678901234567890123456789
        with:
          python-version: "3.12"
""",
                encoding="utf-8",
            )
            self._news(root, "2026-09-24.txt", "2026-09-24")
            self._approved_episode(root, "2026-09-22")

            report = audit_repository(
                repo_root=root,
                as_of=date(2026, 9, 24),
                github_snapshot=self._github(),
            )
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual(checks["python-contract"]["status"], "warn")

    def test_later_successful_backfill_downgrades_historical_build_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            for value in ("2026-09-22", "2026-09-23", "2026-09-24"):
                self._news(root, f"{value}-08-00-00.txt", value)
            self._approved_episode(root, "2026-09-22")
            pages = self._pages(root, "2026-09-22")

            github = self._github()
            for run in github["workflow_runs"]:
                if run["name"] == "Build AI News Video Kit":
                    run["conclusion"] = "failure"
                    run["updated_at"] = "2026-09-24T10:00:00Z"
            github["workflow_runs"].insert(
                0,
                {
                    "id": 99,
                    "name": "Backfill AI News Video Kit",
                    "conclusion": "success",
                    "updated_at": "2026-09-24T13:00:00Z",
                },
            )

            report = audit_repository(
                repo_root=root,
                pages_root=pages,
                as_of=date(2026, 9, 24),
                github_snapshot=github,
                current_workflow_context={},
            )
            checks = {item["id"]: item for item in report["checks"]}
            build = checks["workflow-build-ai-news-video-kit"]

            self.assertEqual(build["status"], "warn")
            self.assertIn("backfill posterior", build["summary"])
            self.assertEqual(report["status_counts"]["critical"], 0)

    def test_current_review_hub_does_not_inherit_previous_completed_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            for value in ("2026-09-22", "2026-09-23", "2026-09-24"):
                self._news(root, f"{value}-08-00-00.txt", value)
            self._approved_episode(root, "2026-09-22")
            pages = self._pages(root, "2026-09-22")

            github = self._github()
            for run in github["workflow_runs"]:
                if run["name"] == "Editorial Review Hub":
                    run["conclusion"] = "failure"
                    run["updated_at"] = "2026-09-24T11:00:00Z"

            report = audit_repository(
                repo_root=root,
                pages_root=pages,
                as_of=date(2026, 9, 24),
                github_snapshot=github,
                current_workflow_context={
                    "workflow": "Editorial Review Hub",
                    "run_id": "220",
                    "run_number": "220",
                    "sha": "abcdef1234567890abcdef1234567890abcdef12",
                    "event_name": "push",
                },
            )
            checks = {item["id"]: item for item in report["checks"]}
            hub = checks["workflow-editorial-review-hub"]

            self.assertEqual(hub["status"], "info")
            self.assertIn("run anterior", hub["summary"])
            self.assertEqual(hub["value"], "run 220")
            self.assertEqual(report["status_counts"]["critical"], 0)
            self.assertEqual(report["snapshot_context"]["run_id"], "220")

            document = health_document(report)
            self.assertIn('data-snapshot-run-id="220"', document)
            self.assertIn('data-snapshot-sha="abcdef123456"', document)
            self.assertIn("commit abcdef123456", document)

    def test_health_page_and_json_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._bootstrap(root)
            self._news(root, "2026-09-24.txt", "2026-09-24")
            self._approved_episode(root, "2026-09-22")
            report = audit_repository(
                repo_root=root,
                as_of=date(2026, 9, 24),
                github_snapshot=self._github(),
            )
            out = root / "out"
            json_path, html_path = write_health_outputs(report, out)

            self.assertTrue(json_path.is_file())
            self.assertTrue(html_path.is_file())
            document = html_path.read_text(encoding="utf-8")
            self.assertIn('data-health-page="repo-health"', document)
            self.assertIn("Salud del repositorio", document)
            self.assertIn("repo-health.json", document)
            self.assertIn("Filtrar checks", health_document(report))


if __name__ == "__main__":
    unittest.main()
