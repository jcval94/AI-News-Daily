from __future__ import annotations

import unittest

from pipeline.evidence_reconciliation import reconcile_evidence_indices


class EvidenceReconciliationTests(unittest.TestCase):
    def test_repairs_distinctive_evidence_ids_only(self) -> None:
        plan = {
            "evidence": [
                {"evidence_id": "traces_benchmark", "selected_news_index": 1},
                {"evidence_id": "aqpotency_predictions", "selected_news_index": 4},
                {"evidence_id": "aqcat_tool_use", "selected_news_index": 3},
            ]
        }
        selected = {
            "items": [
                {"title": "Apodex presenta TRACES", "summary": "Benchmark científico"},
                {"title": "SandboxAQ hace disponible AQCat", "summary": "Catalizadores"},
                {"title": "SandboxAQ lanza AQPotency", "summary": "Moléculas y fármacos"},
                {"title": "Harness lanza agentes de seguridad", "summary": "Vulnerabilidades"},
            ]
        }
        reconciled, changes = reconcile_evidence_indices(plan, selected)
        indices = {
            item["evidence_id"]: item["selected_news_index"]
            for item in reconciled["evidence"]
        }
        self.assertEqual(indices["traces_benchmark"], 1)
        self.assertEqual(indices["aqpotency_predictions"], 3)
        self.assertEqual(indices["aqcat_tool_use"], 2)
        self.assertEqual({item["evidence_id"] for item in changes}, {"aqpotency_predictions", "aqcat_tool_use"})

    def test_generic_or_ambiguous_ids_are_not_rewritten(self) -> None:
        plan = {"evidence": [{"evidence_id": "case_1", "selected_news_index": 2}]}
        selected = {
            "items": [
                {"title": "Caso A", "summary": "IA"},
                {"title": "Caso B", "summary": "IA"},
            ]
        }
        reconciled, changes = reconcile_evidence_indices(plan, selected)
        self.assertEqual(reconciled["evidence"][0]["selected_news_index"], 2)
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
