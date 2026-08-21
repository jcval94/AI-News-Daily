from __future__ import annotations

import unittest
from pathlib import Path


class DependencyLockTests(unittest.TestCase):
    def test_runtime_lock_pins_critical_direct_dependencies(self) -> None:
        lock = Path("requirements.lock").read_text(encoding="utf-8").lower()
        for package in ("google-adk", "google-genai", "litellm", "openai", "pydantic", "requests", "pillow"):
            self.assertRegex(lock, rf"(?m)^{package}==[^\s]+")
        self.assertIn("google-adk==2.6.3", lock)

    def test_ci_and_production_install_with_lock_constraints(self) -> None:
        ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
        prod = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")
        self.assertIn("pip install -c requirements.lock .", ci)
        self.assertIn("pip install -c requirements.lock .", prod)


if __name__ == "__main__":
    unittest.main()
