from pathlib import Path
import unittest


class EssayFirstContractTests(unittest.TestCase):
    def test_director_builds_essay_before_news(self) -> None:
        agent = Path("app/agent.py").read_text(encoding="utf-8")

        self.assertIn(
            "HUMAN EXPERIENCE -> TENSION -> HISTORICAL MIRROR -> CENTRAL QUESTION -> PROVISIONAL THESIS -> CURRENT NEWS AS EVIDENCE",
            agent,
        )
        self.assertIn("Formulate the central question BEFORE deciding which selected stories will appear", agent)
        self.assertIn("News is supporting evidence, never the product itself", agent)
        self.assertIn("Prefer 2-4 strong pieces of evidence to 6-8 shallow mentions", agent)

    def test_writer_rejects_news_desk_opening(self) -> None:
        agent = Path("app/agent.py").read_text(encoding="utf-8")

        self.assertIn("The essay is the product. The news is evidence.", agent)
        self.assertIn("Begin from the human observation/tension in episode_plan.hook, not from a headline", agent)
        self.assertIn("Do NOT default to “hoy salió una noticia”", agent)
        self.assertIn("Never announce “la segunda noticia”", agent)
        self.assertIn("Connect evidence through ideas, not through artificial transitions between headlines", agent)

    def test_editorial_profile_keeps_news_secondary(self) -> None:
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        voice = Path("editorial/voice_profile.md").read_text(encoding="utf-8").lower()

        self.assertIn("el ensayo es el producto", discourse)
        self.assertIn("las noticias son evidencia", discourse)
        self.assertIn("experiencia humana", discourse)
        self.assertIn("tesis", discourse)
        self.assertIn("40% información", voice)
        self.assertIn("60% reflexión", voice)

    def test_follow_up_contract_document_exists(self) -> None:
        contract = Path("docs/essay_first_contract.md").read_text(encoding="utf-8").lower()

        self.assertIn("the essay is the product. the news is evidence.", contract)
        self.assertIn("human observation", contract)
        self.assertIn("historical mirror", contract)
        self.assertIn("evidence strategy", contract)
        self.assertIn("counterexample", contract)
        self.assertIn("limit_case", contract)


if __name__ == "__main__":
    unittest.main()
