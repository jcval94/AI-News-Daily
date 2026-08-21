from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}: {old[:100]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_count(path: str, old: str, new: str, expected: int) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} matches in {path}, found {count}: {old[:100]!r}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


# CRITICAL 1 — make dramaturgy an executable, validated contract.
replace_once(
    "app/agent.py",
    '''class EpisodePlan(BaseModel):
    topic_signature: str = Field(min_length=5, max_length=160)
    narrative_lens: str = Field(min_length=3, max_length=120)
    novelty_angle: str = Field(min_length=5, max_length=400)
    historical_mirror: str = ""
    evidence_strategy: str = Field(min_length=5, max_length=500)
    central_question: str
    thesis: str
    hook: str
    target_duration_minutes: float = Field(ge=7, le=20)
    narrative_arc: List[str] = Field(default_factory=list)
    stories: List[StoryPlan] = Field(default_factory=list)
    final_synthesis: str
    closing_question: str
''',
    '''class NarrativeArc(BaseModel):
    """Required dramaturgical movement; these labels are production metadata, never spoken headings."""

    opening_belief: str = Field(min_length=5, max_length=400)
    central_mystery: str = Field(min_length=5, max_length=400)
    concrete_scene: str = Field(min_length=5, max_length=600)
    first_reveal: str = Field(min_length=5, max_length=500)
    complication: str = Field(min_length=5, max_length=500)
    narrative_turn: str = Field(min_length=5, max_length=500)
    second_reveal: str = Field(min_length=5, max_length=500)
    evolved_thesis: str = Field(min_length=5, max_length=700)
    recurring_motif: str = Field(min_length=1, max_length=160)
    emotional_peak: str = Field(min_length=5, max_length=500)
    final_payoff: str = Field(min_length=5, max_length=600)


class EpisodePlan(BaseModel):
    topic_signature: str = Field(min_length=5, max_length=160)
    narrative_lens: str = Field(min_length=3, max_length=120)
    novelty_angle: str = Field(min_length=5, max_length=400)
    historical_mirror: str = ""
    evidence_strategy: str = Field(min_length=5, max_length=500)
    central_question: str
    thesis: str
    hook: str
    target_duration_minutes: float = Field(ge=7, le=20)
    narrative_arc: NarrativeArc
    stories: List[StoryPlan] = Field(default_factory=list)
    final_synthesis: str
    closing_question: str
''',
)

replace_once(
    "app/agent.py",
    '''NON-NEGOTIABLE EDITORIAL HIERARCHY:
HUMAN EXPERIENCE -> TENSION -> HISTORICAL MIRROR -> CENTRAL QUESTION -> PROVISIONAL THESIS -> CURRENT NEWS AS EVIDENCE.

NOVELTY IS A FIRST-CLASS REQUIREMENT:
''',
    '''NON-NEGOTIABLE EDITORIAL HIERARCHY:
HUMAN EXPERIENCE -> TENSION -> HISTORICAL MIRROR -> CENTRAL QUESTION -> PROVISIONAL THESIS -> CURRENT NEWS AS EVIDENCE.

DRAMATURGY IS ALSO NON-NEGOTIABLE. Populate every narrative_arc field with a distinct job:
- opening_belief: the plausible belief the viewer/narrator starts with;
- central_mystery: an honest unresolved question that creates real intrigue;
- concrete_scene: a vivid real, historical, or explicitly hypothetical scene that makes the tension tangible;
- first_reveal: the first thing the evidence changes in the opening belief;
- complication: evidence that makes the easy answer insufficient;
- narrative_turn: the moment the essay discovers that the more interesting problem is different from the initial one;
- second_reveal: what only becomes visible after that turn;
- evolved_thesis: the richer conclusion reached after the investigation, not a paraphrase of thesis;
- recurring_motif: a short phrase, image, object, or question that can return with changing meaning;
- emotional_peak: the strongest concrete human consequence, without fake sentimentality;
- final_payoff: a resolution that makes the opening feel different in retrospect.

The opening may be extremely intriguing: an unexplained-but-honest scene, counterintuitive claim, strange verified
history, difficult question, contradiction, or clearly labeled hypothetical. Never use empty clickbait. Intrigue
must be paid off. If the exact conclusion is obvious after minute 2, the arc is too flat.

NOVELTY IS A FIRST-CLASS REQUIREMENT:
''',
)

replace_once(
    "app/agent.py",
    '''4. Formulate a provisional thesis that can be complicated or revised during the essay.
5. Compare that question and thesis against previous_essays and establish a real novelty_angle.
6. Only then choose the current stories that help investigate the thesis.
''',
    '''4. Formulate a provisional thesis that can be complicated or revised during the essay.
5. Design the full narrative_arc so the investigation contains mystery, scene, reveal, complication, a genuine
   narrative turn, an evolved thesis, a recurring motif, a human peak, and a final payoff.
6. Compare that question and thesis against previous_essays and establish a real novelty_angle.
7. Only then choose the current stories that help investigate the thesis.
''',
)

replace_once(
    "app/agent.py",
    '''- Plan progressive revelation: the essay should discover and refine an idea rather than announce a conclusion and decorate it with headlines.
- Use curated historical references only; never invent a historical person, quote, date, book, event, or causal claim.
''',
    '''- Plan progressive revelation: the essay should discover and refine an idea rather than announce a conclusion and decorate it with headlines.
- The narrative turn must genuinely reframe the problem; it cannot be a transition sentence.
- narrative_arc.evolved_thesis must be materially richer than the provisional thesis.
- The recurring motif should return only when natural and change meaning across the essay.
- The final payoff should transform how the opening scene, question, or motif is understood.
- Use curated historical references only; never invent a historical person, quote, date, book, event, or causal claim.
''',
)

replace_once(
    "app/agent.py",
    '''- Begin from the human observation/tension in episode_plan.hook, not from a headline.
- The opening should feel like a thoughtful person saying something recognizably true or uncomfortable:
''',
    '''- Begin from the human observation/tension in episode_plan.hook and narrative_arc.opening_belief / central_mystery, not from a headline.
- The opening may be extremely intriguing, but it must be honest and eventually paid off. It may briefly withhold
  explanation; it may not mislead about facts.
- Use narrative_arc.concrete_scene when it makes the mystery tangible.
- Do not reveal the exact evolved thesis in the first two minutes.
- The opening should feel like a thoughtful person saying something recognizably true or uncomfortable:
''',
)

replace_once(
    "app/agent.py",
    '''Narrative requirements:
- Use progressive revelation and genuine open loops, never cheap retention tricks.
- Vary sentence length and section shape.
''',
    '''Narrative requirements:
- Use progressive revelation and genuine open loops, never cheap retention tricks.
- Follow the movement encoded in episode_plan.narrative_arc: opening belief -> mystery -> first reveal ->
  complication -> narrative turn -> second reveal -> evolved thesis -> emotional peak -> final payoff.
- The narrative turn must change the viewer's model of the problem; it is not a transition.
- The evolved thesis must feel earned and richer than episode_plan.thesis.
- Recur to the motif 2-4 times only when natural, allowing its meaning to change.
- The final payoff should make the opening feel different in retrospect.
- Never expose internal labels such as “first reveal”, “narrative turn”, “evidence 1”, or “mini conclusion”.
- Vary sentence length and section shape.
''',
)

replace_once(
    "app/agent.py",
    '''- the first minute makes the viewer want to investigate the idea, not merely hear the week's updates;
- open loops are genuinely paid off;
- pacing has breathing room without dead zones;
- evidence ordering creates discovery, contrast, or revision of the thesis;
- the strongest idea arrives early enough;
- the ending earns its reflective question and CTA.
''',
    '''- the first minute makes the viewer want to investigate the idea, not merely hear the week's updates;
- the central mystery creates a real reason to continue and is eventually paid off;
- the exact final conclusion is not already obvious after minute 2;
- the concrete scene makes an abstract issue tangible;
- the first reveal changes or sharpens the opening belief;
- the complication prevents the easy answer from ending the essay too early;
- the narrative turn genuinely reframes the problem rather than acting as a transition;
- the second reveal earns an evolved thesis richer than the provisional thesis;
- the recurring motif, if used, changes meaning rather than merely repeating;
- the emotional peak is concrete and human without manipulation;
- the final payoff makes the opening feel different in retrospect;
- open loops are genuinely paid off;
- pacing has breathing room without dead zones;
- evidence ordering creates discovery, contrast, or revision of the thesis;
- the ending earns its reflective question and CTA.
''',
)

replace_once(
    "app/agent.py",
    '''Preserve or restore this hierarchy:
HUMAN EXPERIENCE -> TENSION -> HISTORICAL MIRROR -> CENTRAL QUESTION -> THESIS -> NEWS AS EVIDENCE.

Do not open by default with a company, model, benchmark, product, paper, or “today's news”.
''',
    '''Preserve or restore BOTH contracts:
HUMAN EXPERIENCE -> TENSION -> HISTORICAL MIRROR -> CENTRAL QUESTION -> THESIS -> NEWS AS EVIDENCE.
OPENING BELIEF -> MYSTERY -> FIRST REVEAL -> COMPLICATION -> NARRATIVE TURN -> SECOND REVEAL -> EVOLVED THESIS -> PAYOFF.

The narrative turn must genuinely reframe the problem. The evolved thesis must be richer than the provisional
thesis. Reuse the recurring motif only when natural and let its meaning change. Make the payoff transform how the
opening is understood. If the exact conclusion is obvious by minute 2, deepen the mystery/complication rather than
adding filler. Never expose internal dramaturgical labels in narration.

Do not open by default with a company, model, benchmark, product, paper, or “today's news”.
''',
)

# HIGH 1 + HIGH 2 — deduplicate only stories actually covered, and retain the newest 40.
replace_once(
    "pipeline/run.py",
    '''def load_selection_history(scripts_dir: Path, target_date: date, lookback_days: int) -> str:
    cutoff = target_date.fromordinal(target_date.toordinal() - max(1, lookback_days))
    items: list[dict[str, Any]] = []
    if not scripts_dir.exists():
        return "[]"

    for selected_path in sorted(scripts_dir.glob("*/selected_news.json"), reverse=True):
        try:
            episode_date = datetime.strptime(selected_path.parent.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date >= target_date or episode_date < cutoff:
            continue
        reviews_path = selected_path.parent / "reviews.json"
        try:
            reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not bool(reviews.get("approved_for_multimedia", False)):
            continue
        for item in selected.get("items", []):
            if isinstance(item, dict):
                items.append(
                    {
                        "title": item.get("title", ""),
                        "date": item.get("date", ""),
                        "source": item.get("source", ""),
                        "url": item.get("url", ""),
                        "summary": item.get("summary", ""),
                    }
                )
    return json.dumps(items[-40:], ensure_ascii=False)
''',
    '''def load_selection_history(scripts_dir: Path, target_date: date, lookback_days: int) -> str:
    """Return the newest covered stories from approved episodes, never merely selected-but-unused items."""
    cutoff = target_date.fromordinal(target_date.toordinal() - max(1, lookback_days))
    items: list[dict[str, Any]] = []
    if not scripts_dir.exists():
        return "[]"

    episode_dirs = sorted((path for path in scripts_dir.iterdir() if path.is_dir()), reverse=True)
    for episode_dir in episode_dirs:
        try:
            episode_date = datetime.strptime(episode_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if episode_date >= target_date or episode_date < cutoff:
            continue

        selected_path = episode_dir / "selected_news.json"
        reviews_path = episode_dir / "reviews.json"
        plan_path = episode_dir / "episode_plan.json"
        try:
            reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
            selected = json.loads(selected_path.read_text(encoding="utf-8"))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # If an approved legacy episode has no plan, we cannot prove which selected items were narrated.
            # Skipping is safer than incorrectly burning stories that may never have appeared.
            continue
        if not bool(reviews.get("approved_for_multimedia", False)):
            continue

        selected_items = selected.get("items", []) if isinstance(selected, dict) else []
        covered_indices: list[int] = []
        for story in plan.get("stories", []) if isinstance(plan, dict) else []:
            if not isinstance(story, dict):
                continue
            try:
                index = int(story.get("selected_news_index", 0) or 0)
            except (TypeError, ValueError):
                continue
            if index >= 1 and index not in covered_indices:
                covered_indices.append(index)

        for index in covered_indices:
            if not (1 <= index <= len(selected_items)):
                continue
            item = selected_items[index - 1]
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "title": item.get("title", ""),
                    "date": item.get("date", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "summary": item.get("summary", ""),
                }
            )
            if len(items) >= 40:
                return json.dumps(items, ensure_ascii=False)

    return json.dumps(items, ensure_ascii=False)
''',
)

# CRITICAL 2 — production-script generation is part of the promotion invariant.
promotion_condition = '''steps.episode_outcome.outputs.status == 'approved' &&
          steps.report.outcome == 'success' &&
          steps.runtime_options.outputs.promote_approved == 'true' '''
promotion_condition_hardened = '''steps.episode_outcome.outputs.status == 'approved' &&
          steps.production_script.outcome == 'success' &&
          steps.report.outcome == 'success' &&
          steps.runtime_options.outputs.promote_approved == 'true' '''
replace_count(
    ".github/workflows/build-video-kit.yml",
    promotion_condition,
    promotion_condition_hardened,
    expected=2,
)

# Update the mocked orchestration fixture for the now-required structured narrative arc.
replace_once(
    "tests/test_e2e_orchestration.py",
    '''                        "narrative_arc": ["pregunta", "evidencia", "implicacion"],
''',
    '''                        "narrative_arc": {
                            "opening_belief": "Delegar criterio parece una comodidad inocente.",
                            "central_mystery": "¿Qué cambia en nosotros cuando dejamos de verificar?",
                            "concrete_scene": "Imagina una decisión cotidiana que aceptamos sin revisar porque la IA suena segura.",
                            "first_reveal": "La comodidad también modifica el hábito de comprobar.",
                            "complication": "Verificar todo manualmente tampoco escala ni garantiza buen juicio.",
                            "narrative_turn": "El problema deja de ser si la IA piensa y pasa a ser dónde ejercemos criterio.",
                            "second_reveal": "El diseño del proceso decide qué parte del juicio permanece humana.",
                            "evolved_thesis": "Automatizar no elimina el criterio: desplaza el lugar donde debemos ejercerlo conscientemente.",
                            "recurring_motif": "¿Ya quedó?",
                            "emotional_peak": "Una persona puede terminar asumiendo una decisión que nadie revisó realmente.",
                            "final_payoff": "La pregunta ya no es si la herramienta resolvió algo, sino qué significa realmente decir que ya quedó.",
                        },
''',
)

# Strengthen contract tests so dramaturgy must be in executable agent prompts/schema, not only docs.
replace_once(
    "tests/test_essay_first_contract.py",
    '''        self.assertIn("recurring motif", contract)\n''',
    '''        self.assertIn("recurring motif", contract)\n\n        agent = Path("app/agent.py").read_text(encoding="utf-8").lower()\n        self.assertIn("class narrativearc", agent)\n        self.assertIn("narrative_arc: narrativearc", agent)\n        self.assertIn("central_mystery", agent)\n        self.assertIn("narrative_turn", agent)\n        self.assertIn("evolved_thesis", agent)\n        self.assertIn("final_payoff", agent)\n        self.assertIn("if the exact conclusion is obvious after minute 2", agent)\n''',
)

Path("tests/test_selection_history.py").write_text(
    '''from __future__ import annotations\n\nimport json\nimport tempfile\nimport unittest\nfrom datetime import date, timedelta\nfrom pathlib import Path\n\nfrom pipeline.run import load_selection_history\n\n\ndef write_episode(root: Path, episode_date: date, titles: list[str], covered_indices: list[int]) -> None:\n    episode = root / episode_date.isoformat()\n    episode.mkdir(parents=True)\n    (episode / "reviews.json").write_text(json.dumps({"approved_for_multimedia": True}), encoding="utf-8")\n    (episode / "selected_news.json").write_text(\n        json.dumps(\n            {\n                "items": [\n                    {\n                        "title": title,\n                        "date": episode_date.isoformat(),\n                        "source": "source",\n                        "url": f"https://example.com/{title}",\n                        "summary": title,\n                    }\n                    for title in titles\n                ]\n            }\n        ),\n        encoding="utf-8",\n    )\n    (episode / "episode_plan.json").write_text(\n        json.dumps({"stories": [{"selected_news_index": index} for index in covered_indices]}),\n        encoding="utf-8",\n    )\n\n\nclass SelectionHistoryTests(unittest.TestCase):\n    def test_only_covered_stories_are_deduplicated(self) -> None:\n        with tempfile.TemporaryDirectory() as tmp:\n            root = Path(tmp)\n            write_episode(root, date(2026, 8, 20), ["used", "selected-only", "also-used"], [1, 3])\n            history = json.loads(load_selection_history(root, date(2026, 8, 21), 30))\n            self.assertEqual([item["title"] for item in history], ["used", "also-used"])\n\n    def test_legacy_episode_without_plan_does_not_burn_selected_items(self) -> None:\n        with tempfile.TemporaryDirectory() as tmp:\n            root = Path(tmp)\n            episode = root / "2026-08-20"\n            episode.mkdir(parents=True)\n            (episode / "reviews.json").write_text(json.dumps({"approved_for_multimedia": True}), encoding="utf-8")\n            (episode / "selected_news.json").write_text(json.dumps({"items": [{"title": "unknown-use"}]}), encoding="utf-8")\n            history = json.loads(load_selection_history(root, date(2026, 8, 21), 30))\n            self.assertEqual(history, [])\n\n    def test_history_keeps_newest_forty_covered_stories(self) -> None:\n        with tempfile.TemporaryDirectory() as tmp:\n            root = Path(tmp)\n            target = date(2026, 8, 21)\n            for days_ago in range(1, 16):\n                episode_date = target - timedelta(days=days_ago)\n                titles = [f"d{days_ago}-item{i}" for i in range(1, 5)]\n                write_episode(root, episode_date, titles, [1, 2, 3, 4])\n\n            history = json.loads(load_selection_history(root, target, 30))\n            titles = [item["title"] for item in history]\n            self.assertEqual(len(titles), 40)\n            self.assertIn("d1-item1", titles)\n            self.assertIn("d10-item4", titles)\n            self.assertNotIn("d11-item1", titles)\n            self.assertNotIn("d15-item4", titles)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

Path("tests/test_promotion_guard.py").write_text(
    '''from pathlib import Path\nimport unittest\n\n\nclass PromotionGuardTests(unittest.TestCase):\n    def test_production_script_must_succeed_before_promotion(self) -> None:\n        workflow = Path(".github/workflows/build-video-kit.yml").read_text(encoding="utf-8")\n        required = "steps.production_script.outcome == 'success'"\n        self.assertGreaterEqual(workflow.count(required), 2)\n\n        refresh = workflow.split("- name: Refresh branch before promotion", 1)[1].split("- name: Promote approved episode", 1)[0]\n        promote = workflow.split("- name: Promote approved episode", 1)[1].split("- name: Commit approved canonical artifacts", 1)[0]\n        self.assertIn(required, refresh)\n        self.assertIn(required, promote)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
    encoding="utf-8",
)

print("Applied critical/high-1/high-2 hardening only.")
