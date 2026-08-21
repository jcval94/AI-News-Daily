from pathlib import Path
import unittest


class EditorialLanguageContractTests(unittest.TestCase):
    def test_editorial_profiles_avoid_strong_rioplatense_contract(self) -> None:
        voice = Path("editorial/voice_profile.md").read_text(encoding="utf-8").lower()
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()

        # The words may appear only inside explicit anti-style rules in prompts/profiles.
        # The positive voice definition must no longer describe the target as Rioplatense/voseo.
        self.assertNotIn("español rioplatense", voice)
        self.assertNotIn("voseo ligero", voice)
        self.assertNotIn("educated, natural rioplatense", agent)
        self.assertNotIn("light, natural voseo", agent)

        self.assertIn("español latinoamericano neutral", voice)
        self.assertIn("ligera cercanía mexicana", voice)
        self.assertIn("curioso, pero no necesariamente técnico", discourse)

    def test_historical_opening_is_curated_and_source_backed(self) -> None:
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        self.assertIn("apertura: noticia → historia → pregunta", discourse)
        self.assertIn("referentes históricos curados", discourse)
        self.assertIn("plato.stanford.edu", discourse)
        self.assertIn("smithsonianmag.com", discourse)
        self.assertIn("nber.org", discourse)
        self.assertIn("computerhistory.org", discourse)
        self.assertIn("nunca inventar una cita", discourse)

    def test_writer_contract_prefers_plain_language(self) -> None:
        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()
        self.assertIn("curious 15-year-old", agent)
        self.assertIn("prefer common spanish over jargon", agent)
        self.assertIn("current news → verified historical parallel → deeper question", agent)
        self.assertIn("fact, interpretation, hypothesis, and uncertainty", agent)
        self.assertIn("punzadura", agent)  # explicit negative example, not target vocabulary


if __name__ == "__main__":
    unittest.main()
