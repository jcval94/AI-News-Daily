from pathlib import Path


def rw(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Keep the explicit essay-first phrase relied upon by runtime/document contract tests.
rw(
    "app/agent.py",
    "EVIDENCE AND BEATS — KEEP THEM SEPARATE:\n- episode_plan.evidence is a catalog of current-news evidence, NOT the section structure.\n",
    "EVIDENCE AND BEATS — KEEP THEM SEPARATE:\n- News is supporting evidence, never the product itself.\n- episode_plan.evidence is a catalog of current-news evidence, NOT the section structure.\n",
)

# Preserve history across the architecture migration: new plans use beats; older approved modern plans may still use stories.
rw(
    "pipeline/run.py",
'''        selected_items = selected.get("items", []) if isinstance(selected, dict) else []
        covered_indices: list[int] = []
        for beat in plan.get("beats", []) if isinstance(plan, dict) else []:
            if not isinstance(beat, dict):
                continue
            for raw_index in beat.get("evidence_news_indices", []):
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    continue
                if index >= 1 and index not in covered_indices:
                    covered_indices.append(index)
''',
'''        selected_items = selected.get("items", []) if isinstance(selected, dict) else []
        covered_indices: list[int] = []
        beats = plan.get("beats", []) if isinstance(plan, dict) else []
        if beats:
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                for raw_index in beat.get("evidence_news_indices", []):
                    try:
                        index = int(raw_index)
                    except (TypeError, ValueError):
                        continue
                    if index >= 1 and index not in covered_indices:
                        covered_indices.append(index)
        else:
            # Transitional compatibility for approved pre-beat plans. Legacy/incomplete plans are already skipped above.
            for story in plan.get("stories", []) if isinstance(plan, dict) else []:
                if not isinstance(story, dict):
                    continue
                try:
                    index = int(story.get("selected_news_index", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if index >= 1 and index not in covered_indices:
                    covered_indices.append(index)
''',
)

rw(
    "tests/test_e2e_orchestration.py",
'''        script = ("<!--SECTION:opening-->" + " ".join(["noticia"] * 250) + " <!--SECTION:beat:evidence-->" + " ".join(["noticia"] * 600) + " <!--SECTION:synthesis-->" + " ".join(["noticia"] * 200))
''',
'''        script = ("<!--SECTION:opening-->" + " ".join(["noticia"] * 250) + " <!--SECTION:beat:evidence-->" + " ".join(["noticia"] * 500) + " <!--SECTION:beat:turn-->" + " ".join(["noticia"] * 100) + " <!--SECTION:synthesis-->" + " ".join(["noticia"] * 200))
''',
)

rw(
    "tests/test_e2e_failure_paths.py",
'''    return (
        "<!--SECTION:opening-->" + " ".join(["inicio"] * 250) +
        " <!--SECTION:beat:evidence-->" + " ".join(["desarrollo"] * 600) +
        " <!--SECTION:synthesis-->" + " ".join(["cierre"] * 200)
    )
''',
'''    return (
        "<!--SECTION:opening-->" + " ".join(["inicio"] * 250) +
        " <!--SECTION:beat:evidence-->" + " ".join(["desarrollo"] * 500) +
        " <!--SECTION:beat:turn-->" + " ".join(["giro"] * 100) +
        " <!--SECTION:synthesis-->" + " ".join(["cierre"] * 200)
    )
''',
)

print("validation migration fixes applied")
