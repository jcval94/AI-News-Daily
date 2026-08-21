from pathlib import Path
import unittest


class EditorialLanguageContractTests(unittest.TestCase):
    def test_editorial_profiles_avoid_strong_rioplatense_contract(self) -> None:
        voice = Path("editorial/voice_profile.md").read_text(encoding="utf-8").lower()
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()

        self.assertNotIn("español rioplatense", voice)
        self.assertNotIn("voseo ligero", voice)
        self.assertNotIn("educated, natural rioplatense", agent)
        self.assertNotIn("light, natural voseo", agent)

        self.assertIn("español latinoamericano neutral", voice)
        self.assertIn("ligera cercanía mexicana", voice)
        self.assertIn("curioso, pero no necesariamente técnico", discourse)

    def test_historical_context_is_curated_and_source_backed(self) -> None:
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        self.assertIn("apertura: experiencia → tensión → historia → pregunta", discourse)
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
        self.assertIn("fact, interpretation, hypothesis, and uncertainty", agent)
        self.assertIn("punzadura", agent)  # explicit negative example, not target vocabulary

    def test_essay_is_primary_and_news_is_evidence(self) -> None:
        voice = Path("editorial/voice_profile.md").read_text(encoding="utf-8").lower()
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()

        self.assertIn("la noticia no es el producto", voice)
        self.assertIn("la noticia es evidencia", voice)
        self.assertIn("experiencia humana → tensión → espejo histórico → tesis → noticias como evidencia", discourse)
        self.assertIn("news is supporting evidence, never the product itself", agent)
        self.assertIn("the essay is the product. the news is evidence", agent)
        self.assertIn("do not write a news recap", agent)
        self.assertIn("human experience -> tension -> historical mirror", agent)

    def test_opening_rejects_news_desk_default(self) -> None:
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()

        self.assertIn("“hoy salió una noticia…” como apertura por defecto", discourse)
        self.assertIn("do not default to “hoy salió una noticia”", agent)
        self.assertIn("opening with “hoy salió una noticia”", agent)
        self.assertIn("news-desk structure", agent)


if __name__ == "__main__":
    unittest.main()
