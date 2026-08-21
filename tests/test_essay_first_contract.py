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
        self.assertIn("Begin from the human observation/tension in episode_plan.hook and narrative_arc.opening_belief / central_mystery, not from a headline", agent)
        self.assertIn("Do NOT default to “hoy salió una noticia”", agent)
        self.assertIn("Never announce “la segunda noticia”", agent)
        self.assertIn("Connect evidence through ideas, not through artificial transitions between headlines", agent)

    def test_editorial_profile_keeps_news_secondary(self) -> None:
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        voice = Path("editorial/voice_profile.md").read_text(encoding="utf-8").lower()

        self.assertIn("experiencia humana → tensión → espejo histórico → tesis → noticias como evidencia", discourse)
        self.assertIn("la noticia no es el producto", voice)
        self.assertIn("el ensayo es el producto", voice)
        self.assertIn("40% información y 60% reflexión", voice)
        self.assertIn("no organizar el episodio como “noticia 1, noticia 2, noticia 3”", voice)

    def test_follow_up_contract_document_exists(self) -> None:
        contract = Path("docs/essay_first_contract.md").read_text(encoding="utf-8").lower()

        self.assertIn("the essay is the product. the news is evidence.", contract)
        self.assertIn("human observation", contract)
        self.assertIn("historical mirror", contract)
        self.assertIn("evidence strategy", contract)
        self.assertIn("counterexample", contract)
        self.assertIn("limit_case", contract)

    def test_dramaturgy_requires_intrigue_turn_and_payoff(self) -> None:
        discourse = Path("editorial/discourse_profile.md").read_text(encoding="utf-8").lower()
        contract = Path("docs/essay_first_contract.md").read_text(encoding="utf-8").lower()

        self.assertIn("intriga extrema, pero honesta", discourse)
        self.assertIn("dramaturgia obligatoria del ensayo", discourse)
        self.assertIn("central mystery", discourse)
        self.assertIn("narrative turn", discourse)
        self.assertIn("evolved thesis", discourse)
        self.assertIn("recurring motif", discourse)
        self.assertIn("final payoff", discourse)
        self.assertIn("si el espectador podría adivinar la conclusión exacta después del minuto 2", discourse)
        self.assertIn("opening belief → mystery → evidence → first reveal", contract)
        self.assertIn("the exact conclusion is obvious after minute 2", contract)
        self.assertIn("recurring motif", contract)

        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()
        self.assertIn("class narrativearc", agent)
        self.assertIn("narrative_arc: narrativearc", agent)
        self.assertIn("central_mystery", agent)
        self.assertIn("narrative_turn", agent)
        self.assertIn("evolved_thesis", agent)
        self.assertIn("final_payoff", agent)
        self.assertIn("if the exact conclusion is obvious after minute 2", agent)


if __name__ == "__main__":
    unittest.main()
