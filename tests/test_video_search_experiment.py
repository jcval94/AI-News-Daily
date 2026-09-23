import argparse
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.video_search import plan, providers, run


def sample_plan():
    return plan.validate_plan({
        "theme": {"mention": "malas prácticas financieras", "queries": ["financial misconduct"],
                  "match_groups": [["financial", "fraud"]]},
        "events": [{"mention": "caída de Enron", "queries": ["Enron collapse", "Enron scandal"],
                    "match_groups": [["enron", "collapse"], ["enron", "fraud"]]}],
    }, "Malas prácticas financieras y la caída de Enron")


class VideoSearchTests(unittest.TestCase):
    def test_grounded_event_and_aliases(self):
        p = sample_plan()
        self.assertTrue(plan.matches(p.events[0], "The collapse of Enron in 2001"))
        self.assertFalse(plan.matches(p.events[0], "Enron logo animation"))
        self.assertFalse(plan.matches(p.events[0], "Generic financial fraud"))
        raw = p.model_dump()
        raw["events"][0]["mention"] = "Lehman Brothers"
        with self.assertRaises(ValueError):
            plan.validate_plan(raw, "la caída de Enron")

    def test_unknown_subject_literal_is_explicitly_degraded(self):
        p, meta = plan.make_plan("arrecifes de coral", "literal", None)
        self.assertEqual(p.theme.queries, ["arrecifes de coral"])
        self.assertFalse(meta["event_detection"])

    def test_semantic_does_not_silently_degrade_without_secret(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(RuntimeError):
            plan.make_plan("Segunda Guerra Mundial", "semantic", None)

    def test_schema_extra_fields_and_urls_rejected(self):
        raw = sample_plan().model_dump()
        raw["command"] = "rm -rf anything"
        with self.assertRaises(ValueError):
            plan.validate_plan(raw, "caída de Enron")
        del raw["command"]
        raw["theme"]["queries"] = ["https://internal.example"]
        with self.assertRaises(ValueError):
            plan.validate_plan(raw, "caída de Enron")

    def test_discovery_deduplicates_and_retains_event_specific_candidates(self):
        specific = providers.candidate("youtube", "12345678901", "Enron fraud", "", "A", "unknown", "q")
        generic = providers.candidate("youtube", "12345678902", "Financial fraud", "", "B", "unknown", "q")
        with patch.object(providers, "youtube_search", return_value=[generic, specific]):
            candidates, attempts = providers.discover(sample_plan(), ["youtube"])
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["events"], ["caída de Enron"])
        self.assertEqual(len(attempts), 3)

    def test_provider_block_stops_queries_but_keeps_other_source(self):
        with patch.object(providers, "youtube_search", side_effect=providers.ProviderBlocked("blocked")) as youtube:
            with patch.object(providers, "archive_search", return_value=[]) as archive:
                _, attempts = providers.discover(sample_plan(), ["youtube", "archive"])
        self.assertEqual(youtube.call_count, 1)
        self.assertEqual(archive.call_count, 3)
        self.assertIn("skipped_provider_blocked", [a["status"] for a in attempts])

    def test_archive_restricted_and_path_traversal_rejected(self):
        item = {"id": "sample"}
        for data in [{"metadata": {"access-restricted-item": "true"}},
                     {"metadata": {}, "files": [{"name": "../escape.mp4", "size": "100"}]}]:
            with patch.object(providers, "request_json", return_value=data):
                with self.assertRaises((ValueError, RuntimeError)):
                    providers.archive_media(item)

    def test_missing_event_cannot_pass_count_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = {"config": {"count": 1, "mode": "clip", "sources": ["youtube"]},
                        "plan": sample_plan().model_dump(), "items": [dict(
                            providers.candidate("youtube", "12345678901", "Financial fraud", "", "A", "unknown", "q"),
                            status="downloaded", metadata={})]}
            self.assertFalse(run.write_report(Path(directory), manifest))
            self.assertEqual(manifest["summary"]["missing_events"], ["caída de Enron"])

    def test_download_block_preserves_diagnostics_and_is_not_success(self):
        p = sample_plan()
        item = providers.candidate("youtube", "12345678901", "Enron fraud", "", "A", "unknown", "q")
        item.update(relevant=True, events=["caída de Enron"])
        args = argparse.Namespace(description="caída de Enron", count=1, sources="youtube", mode="clip",
                                  clip_seconds=15, planner="semantic")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(run, "make_plan", return_value=(p, {})), patch.object(run, "discover", return_value=([item], [])):
                with patch.object(run, "assess_candidates", return_value={}), patch.object(run, "download", side_effect=providers.ProviderBlocked("not a bot")) as download:
                    self.assertFalse(run.execute(args, Path(directory)))
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(download.call_count, 1)
            self.assertEqual(manifest["summary"]["downloaded"], 0)
            self.assertIn("youtube", manifest["blocked_sources"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "requires media tools")
    def test_real_media_is_decodable_and_truncated_full_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=320x180:d=1",
                            "-c:v", "libx264", "-y", str(path)], check=True)
            self.assertEqual(run.validate_media(path, "clip", 15)["height"], 180)
            with self.assertRaisesRegex(RuntimeError, "truncated"):
                run.validate_media(path, "full", 15, expected_duration=100)

    def test_errors_redact_credentials_and_remote_urls(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "secret-test"}):
            text = providers.safe_error("secret-test https://example.com?token=signed")
        self.assertNotIn("secret-test", text)
        self.assertNotIn("signed", text)

    def test_semantic_selection_rejects_incidental_matches_and_unknown_ids(self):
        candidates = [dict(providers.candidate("archive", ident, title, "Enron fraud", "A", "unknown", "q"),
                           relevant=True, events=["caída de Enron"])
                      for ident, title in [("focused", "Enron collapse"), ("incidental", "Football in 2001")]]
        selections = {"selected": [{"key": "c001", "event_mentions": ["caída de Enron"],
                                    "reason": "Trata específicamente el colapso de Enron."}]}
        def response(*args, **kwargs):
            enum = kwargs['body']['text']['format']['schema']['$defs']['Selection']['properties']['key']['enum']
            self.assertIn('c001', enum)
            self.assertNotIn('archive:focused', enum)
            return {"status": "completed", "output": [{"content": [{"type": "output_text",
                                                                       "text": json.dumps(selections)}]}]}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test"}):
            selections["selected"].append(dict(selections["selected"][0]))
            assessment = plan.assess_candidates(sample_plan(), candidates, response)
            self.assertEqual(assessment["duplicate_proposals_dropped"], 1)
            self.assertEqual(assessment["selected"], 1)
            self.assertTrue(candidates[0]["relevant"])
            self.assertFalse(candidates[1]["relevant"])
            selections["selected"][0]["key"] = "c999"
            with self.assertRaisesRegex(ValueError, "Unknown"):
                plan.assess_candidates(sample_plan(), candidates, response)


if __name__ == "__main__":
    unittest.main()
