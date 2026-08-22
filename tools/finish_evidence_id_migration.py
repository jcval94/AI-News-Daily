from pathlib import Path

path = Path("pipeline/production_script.py")
text = path.read_text(encoding="utf-8")
text = text.replace('"evidence_news_indices": [],', '"evidence_ids": [],')
path.write_text(text, encoding="utf-8")

path = Path("tests/test_script_sections.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    'self.assertEqual(payload["sections"][1]["evidence_ids"], [2, 5])',
    'self.assertEqual(payload["sections"][1]["evidence_ids"], ["case-a", "case-b"])',
)
path.write_text(text, encoding="utf-8")

for product_path in (
    "app/agent.py",
    "pipeline/run.py",
    "pipeline/script_sections.py",
    "pipeline/production_script.py",
):
    if "evidence_news_indices" in Path(product_path).read_text(encoding="utf-8"):
        raise RuntimeError(f"ambiguous evidence_news_indices remains in {product_path}")

print("remaining evidence-id metadata normalized")
