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

    def test_pages_process_is_rendered_from_manifest(self) -> None:
        panel = process_panel({"totals": {}, "usage": {}, "breakdown_by_step": [], "attempts": []})
        self.assertIn("pipeline/architecture_manifest.py", panel)
        self.assertIn("Living architecture", panel)
        self.assertIn("Mapa de decisiones", panel)
        self.assertIn("trace: refine_factual", panel)
        self.assertIn("factual_refiner_agent", panel)
        self.assertIn("La documentación también debe pasar un gate", panel)


if __name__ == "__main__":
    unittest.main()
