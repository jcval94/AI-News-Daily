from pathlib import Path
import unittest


class TopicNoveltyContractTests(unittest.TestCase):
    def test_novelty_design_is_documented(self) -> None:
        text = Path("docs/topic_novelty_design.md").read_text(encoding="utf-8").lower()
        self.assertIn("essay-topic deduplication", text)
        self.assertIn("previous_essays", text)
        self.assertIn("topic_signature", text)
        self.assertIn("no_novel_essay_angle", text)
        self.assertIn("why not solve this with temperature", text)


if __name__ == "__main__":
    unittest.main()
