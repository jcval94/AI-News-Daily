from __future__ import annotations

import unittest

from pipeline.architecture_manifest import manifest
from pipeline.review_hub_v10 import process_panel, validate_manifest_runtime


class ArchitectureManifestTests(unittest.TestCase):
    def test_manifest_resolves_runtime_agent_symbols(self) -> None:
        errors = validate_manifest_runtime(manifest())
        self.assertEqual(errors, [])

    def test_manifest_has_current_refinement_contract(self) -> None:
        data = manifest()
        names = {agent["name"] for agent in data["agents"]}
        self.assertIn("factual_script_refiner", names)
        self.assertIn("voice_script_refiner", names)
        self.assertIn("secondary_script_refiner", names)
        self.assertNotIn("script_refiner", names)
        self.assertEqual(
            [phase["id"] for phase in data["refinement_phases"]],
            ["factual", "voice", "secondary"],
        )
        self.assertEqual(
            [phase["trace_step"] for phase in data["refinement_phases"]],
            ["refine_factual", "refine_voice", "refine_secondary"],
        )

    def test_manifest_tracks_hardened_production_contract(self) -> None:
        data = manifest()
        stages = {stage["id"]: stage for stage in data["stages"]}
        self.assertEqual(data["version"], 12)
        self.assertIn("source_coverage", stages)
        self.assertIn("narrative_memory", stages)
        self.assertIn("narrative_memory_observability", stages)
        self.assertIn("1–2", stages["narrative_memory"]["summary"])
        self.assertIn("abrir el ensayo", stages["narrative_memory"]["summary"])
        self.assertIn("pages-site/memory", stages["narrative_memory_observability"]["outputs"])
        self.assertIn("pipeline/narrative_memory.py", stages["narrative_memory"]["code"])
        self.assertIn("75%", stages["source_coverage"]["summary"])
        self.assertIn("post-aprobación", stages["media_plan"]["title"])
        self.assertIn("footage_discovery", stages)
        self.assertIn("YouTube", stages["footage_discovery"]["title"])
        self.assertIn("30-day ephemeral", stages["footage_discovery"]["outputs"])
        self.assertIn("revisión humana", stages["footage_discovery"]["authority"])
        self.assertIn("editing_style", stages)
        self.assertIn("Gramática audiovisual", stages["editing_style"]["title"])
        self.assertIn("style_warnings", stages["editing_style"]["outputs"])
        self.assertIn("editing_style.yaml", stages["editing_style"]["code"])
        self.assertIn("edit_manifest", stages)
        self.assertIn("pre-recording", stages["edit_manifest"]["title"])
        self.assertIn("edit_manifest.json", stages["edit_manifest"]["outputs"])
        self.assertIn("recording_pack", stages)
        self.assertIn("teleprompter", stages["recording_pack"]["title"].lower())
        self.assertIn("camera_script.md", stages["recording_pack"]["outputs"])
        self.assertIn("script.txt", stages["recording_pack"]["authority"])
        self.assertIn("virtual_timeline", stages)
        self.assertIn("Virtual A-roll", stages["virtual_timeline"]["title"])
        self.assertIn("virtual_timeline.json", stages["virtual_timeline"]["outputs"])
        self.assertIn("timeline_preview.html", stages["virtual_timeline"]["outputs"])
        self.assertIn("not frame-accurate", stages["virtual_timeline"]["authority"])
        self.assertIn("otio_export", stages)
        self.assertIn("OpenTimelineIO", stages["otio_export"]["title"])
        self.assertIn("timeline.otio", stages["otio_export"]["outputs"])
        self.assertIn("round-trip", stages["otio_export"]["summary"])
        self.assertIn("otio_export.py", stages["otio_export"]["code"])
        self.assertIn("placeholder_media", stages)
        self.assertIn("Placeholder media", stages["placeholder_media"]["title"])
        self.assertIn("placeholder_manifest.json", stages["placeholder_media"]["outputs"])
        self.assertIn("resolve_bridge", stages)
        self.assertIn("DaVinci Resolve", stages["resolve_bridge"]["title"])
        self.assertIn("resolve_bridge_plan.json", stages["resolve_bridge"]["outputs"])
        self.assertIn("DaVinciResolveScript", stages["resolve_bridge"]["authority"])
        self.assertIn("pre_recording_preview", stages)
        self.assertIn("Pre-recording Preview", stages["pre_recording_preview"]["title"])
        self.assertIn("pre_recording_preview_plan.json", stages["pre_recording_preview"]["outputs"])
        self.assertIn("artifact aislado", stages["pre_recording_preview"]["outputs"])
        self.assertIn("FFmpeg", stages["pre_recording_preview"]["authority"])
        self.assertIn("ai-news-run", stages["pages"]["inputs"])
        self.assertIn("fuente canónica", stages["pages"]["summary"])

    def test_pages_process_is_rendered_from_manifest(self) -> None:
        panel = process_panel({"totals": {}, "usage": {}, "breakdown_by_step": [], "attempts": []})
        self.assertIn("pipeline/architecture_manifest.py", panel)
        self.assertIn("Living architecture", panel)
        self.assertIn("Mapa de decisiones", panel)
        self.assertIn("trace: refine_factual", panel)
        self.assertIn("factual_refiner_agent", panel)
        self.assertIn("Build AI News Video Kit", panel)
        self.assertIn("ai-news-run artifact", panel)
        self.assertIn("Lane B · QA", panel)
        self.assertIn("La documentación también debe pasar un gate", panel)


if __name__ == "__main__":
    unittest.main()
