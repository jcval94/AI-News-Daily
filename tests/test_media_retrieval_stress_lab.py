from __future__ import annotations

import unittest

from experiments.media_retrieval_stress.harness.selftest import main as run_stress_selftest


class MediaRetrievalStressLabTests(unittest.TestCase):
    def test_offline_contracts_fixtures_mutations_and_gates(self) -> None:
        run_stress_selftest()


if __name__ == "__main__":
    unittest.main()
