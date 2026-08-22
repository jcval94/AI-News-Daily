from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, got {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


# app models + prompts
path = "app/agent.py"
text = read(path)
text = text.replace(
    "class EvidencePlan(BaseModel):\n    selected_news_index: int = Field(ge=1)\n",
    "class EvidencePlan(BaseModel):\n    evidence_id: str = Field(pattern=r\"^[a-z0-9][a-z0-9_-]{0,31}$\")\n    selected_news_index: int = Field(ge=1)\n",
    1,
)
text = text.replace(
    "    evidence_news_indices: List[int] = Field(default_factory=list, max_length=4)\n",
    "    evidence_ids: List[str] = Field(default_factory=list, max_length=4)\n",
    1,
)
old_validator = '''        evidence_indices = [item.selected_news_index for item in self.evidence]
        if len(evidence_indices) != len(set(evidence_indices)):
            raise ValueError("episode_plan.evidence must not duplicate selected news")
        beat_ids = [beat.beat_id for beat in self.beats]
        if len(beat_ids) != len(set(beat_ids)):
            raise ValueError("episode_plan.beats must use unique beat_id values")
        planned = set(evidence_indices)
        used: set[int] = set()
        for beat in self.beats:
            if len(beat.evidence_news_indices) != len(set(beat.evidence_news_indices)):
                raise ValueError(f"beat {beat.beat_id} repeats an evidence index")
            unexpected = set(beat.evidence_news_indices) - planned
            if unexpected:
                raise ValueError(
                    f"beat {beat.beat_id} references evidence not declared in episode_plan.evidence: {sorted(unexpected)}"
                )
            used.update(beat.evidence_news_indices)
        if planned - used:
            raise ValueError(
                "Every episode_plan.evidence item must serve at least one narrative beat; "
                f"unused={sorted(planned - used)}"
            )
'''
new_validator = '''        evidence_indices = [item.selected_news_index for item in self.evidence]
        if len(evidence_indices) != len(set(evidence_indices)):
            raise ValueError("episode_plan.evidence must not duplicate selected news")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("episode_plan.evidence must use unique evidence_id values")
        beat_ids = [beat.beat_id for beat in self.beats]
        if len(beat_ids) != len(set(beat_ids)):
            raise ValueError("episode_plan.beats must use unique beat_id values")
        planned = set(evidence_ids)
        used: set[str] = set()
        for beat in self.beats:
            if len(beat.evidence_ids) != len(set(beat.evidence_ids)):
                raise ValueError(f"beat {beat.beat_id} repeats an evidence_id")
            unexpected = set(beat.evidence_ids) - planned
            if unexpected:
                raise ValueError(
                    f"beat {beat.beat_id} references undeclared evidence_id values: {sorted(unexpected)}"
                )
            used.update(beat.evidence_ids)
        if planned - used:
            raise ValueError(
                "Every episode_plan.evidence item must serve at least one narrative beat; "
                f"unused evidence_id values={sorted(planned - used)}"
            )
'''
if text.count(old_validator) != 1:
    raise RuntimeError("app/agent.py validator block changed")
text = text.replace(old_validator, new_validator, 1)
text = text.replace("evidence_news_indices", "evidence_ids")
text = text.replace(
    "- episode_plan.evidence is a catalog of current-news evidence, NOT the section structure.\n",
    "- episode_plan.evidence is a catalog of current-news evidence, NOT the section structure. Give every evidence item a stable, semantic evidence_id such as `traces` or `aqpotency`; evidence_id is NOT a list position.\n",
    1,
)
text = text.replace(
    "Evidence selected_news_index values are 1-based and MUST refer to selected_news.items. Beat evidence_ids must refer only to indices declared in episode_plan.evidence.\n",
    "Evidence selected_news_index values are 1-based and MUST refer to selected_news.items. Each evidence item also owns a stable evidence_id. Beats reference evidence ONLY by those evidence_id strings; never use selected-news positions inside beats.\n",
    1,
)
write(path, text)

# run.py history + validation
path = "pipeline/run.py"
text = read(path)
old_history = '''        beats = plan.get("beats", []) if isinstance(plan, dict) else []
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
'''
new_history = '''        beats = plan.get("beats", []) if isinstance(plan, dict) else []
        if beats:
            evidence_lookup: dict[str, int] = {}
            for evidence in plan.get("evidence", []) if isinstance(plan, dict) else []:
                if not isinstance(evidence, dict):
                    continue
                evidence_id = str(evidence.get("evidence_id", "") or "").strip()
                try:
                    selected_index = int(evidence.get("selected_news_index", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if evidence_id and selected_index >= 1:
                    evidence_lookup[evidence_id] = selected_index
            for beat in beats:
                if not isinstance(beat, dict):
                    continue
                for evidence_id in beat.get("evidence_ids", []):
                    index = evidence_lookup.get(str(evidence_id), 0)
                    if index >= 1 and index not in covered_indices:
                        covered_indices.append(index)
        else:
'''
if text.count(old_history) != 1:
    raise RuntimeError("pipeline/run.py history block changed")
text = text.replace(old_history, new_history, 1)
old_validate = '''    evidence_indices: list[int] = []
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Every episode_plan evidence item must be an object")
        index = int(item.get("selected_news_index", 0) or 0)
        if index < 1 or index > selected_count:
            raise ValueError("episode_plan evidence references selected news outside the catalog")
        evidence_indices.append(index)
    if len(evidence_indices) != len(set(evidence_indices)):
        raise ValueError("episode_plan.evidence must not duplicate selected news")

    allowed = set(evidence_indices)
    used: set[int] = set()
    beat_ids: list[str] = []
    for beat in beats:
        if not isinstance(beat, dict):
            raise ValueError("Every episode_plan beat must be an object")
        beat_id = str(beat.get("beat_id", "") or "").strip()
        if not beat_id:
            raise ValueError("Every episode_plan beat must have beat_id")
        beat_ids.append(beat_id)
        raw_indices = beat.get("evidence_news_indices", [])
        indices = [int(value) for value in raw_indices]
        if len(indices) != len(set(indices)):
            raise ValueError(f"Beat {beat_id} repeats an evidence index")
        if set(indices) - allowed:
            raise ValueError(f"Beat {beat_id} references evidence not declared in episode_plan.evidence")
        used.update(indices)
    if len(beat_ids) != len(set(beat_ids)):
        raise ValueError("episode_plan beat_id values must be unique")
    if allowed - used:
        raise ValueError("Every declared evidence item must serve at least one beat")
'''
new_validate = '''    evidence_indices: list[int] = []
    evidence_ids: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("Every episode_plan evidence item must be an object")
        index = int(item.get("selected_news_index", 0) or 0)
        if index < 1 or index > selected_count:
            raise ValueError("episode_plan evidence references selected news outside the catalog")
        evidence_id = str(item.get("evidence_id", "") or "").strip()
        if not evidence_id:
            raise ValueError("Every episode_plan evidence item must have evidence_id")
        evidence_indices.append(index)
        evidence_ids.append(evidence_id)
    if len(evidence_indices) != len(set(evidence_indices)):
        raise ValueError("episode_plan.evidence must not duplicate selected news")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("episode_plan.evidence must use unique evidence_id values")

    allowed = set(evidence_ids)
    used: set[str] = set()
    beat_ids: list[str] = []
    for beat in beats:
        if not isinstance(beat, dict):
            raise ValueError("Every episode_plan beat must be an object")
        beat_id = str(beat.get("beat_id", "") or "").strip()
        if not beat_id:
            raise ValueError("Every episode_plan beat must have beat_id")
        beat_ids.append(beat_id)
        refs = [str(value) for value in beat.get("evidence_ids", [])]
        if len(refs) != len(set(refs)):
            raise ValueError(f"Beat {beat_id} repeats an evidence_id")
        if set(refs) - allowed:
            raise ValueError(f"Beat {beat_id} references undeclared evidence_id values")
        used.update(refs)
    if len(beat_ids) != len(set(beat_ids)):
        raise ValueError("episode_plan beat_id values must be unique")
    if allowed - used:
        raise ValueError("Every declared evidence item must serve at least one beat")
'''
if text.count(old_validate) != 1:
    raise RuntimeError("pipeline/run.py validate block changed")
text = text.replace(old_validate, new_validate, 1)
write(path, text)

# script sections metadata
path = "pipeline/script_sections.py"
text = read(path).replace("evidence_news_indices", "evidence_ids")
write(path, text)

# production mapping evidence_id -> selected news index
path = "pipeline/production_script.py"
text = read(path)
old = '''    beats = episode_plan.get("beats", []) if isinstance(episode_plan, dict) else []
    beats = [beat for beat in beats if isinstance(beat, dict)]
    selected_items = selected_news.get("items", []) if isinstance(selected_news, dict) else []
'''
new = '''    beats = episode_plan.get("beats", []) if isinstance(episode_plan, dict) else []
    beats = [beat for beat in beats if isinstance(beat, dict)]
    evidence_catalog = episode_plan.get("evidence", []) if isinstance(episode_plan, dict) else []
    evidence_by_id = {
        str(item.get("evidence_id", "")): item
        for item in evidence_catalog
        if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
    }
    selected_items = selected_news.get("items", []) if isinstance(selected_news, dict) else []
'''
if text.count(old) != 1:
    raise RuntimeError("production catalog insertion point changed")
text = text.replace(old, new, 1)
old = '''        evidence_indices = [int(value) for value in beat.get("evidence_news_indices", [])]
        titles: list[str] = []
        for selected_index in evidence_indices:
            if 1 <= selected_index <= len(selected_items):
                item = selected_items[selected_index - 1]
                if isinstance(item, dict):
                    title = str(item.get("title", "") or "").strip()
                    if title:
                        titles.append(title)
'''
new = '''        evidence_ids = [str(value) for value in beat.get("evidence_ids", [])]
        selected_indices: list[int] = []
        titles: list[str] = []
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id, {})
            try:
                selected_index = int(evidence.get("selected_news_index", 0) or 0)
            except (TypeError, ValueError):
                continue
            selected_indices.append(selected_index)
            if 1 <= selected_index <= len(selected_items):
                item = selected_items[selected_index - 1]
                if isinstance(item, dict):
                    title = str(item.get("title", "") or "").strip()
                    if title:
                        titles.append(title)
'''
if text.count(old) != 1:
    raise RuntimeError("production beat evidence block changed")
text = text.replace(old, new, 1)
text = text.replace('            "evidence_news_indices": evidence_indices,\n', '            "evidence_ids": evidence_ids,\n            "selected_news_indices": selected_indices,\n', 1)
write(path, text)

# Tests and fixtures: migrate mechanically, then add stable IDs to each evidence catalog.
for path in [
    "tests/test_script_sections.py",
    "tests/test_editorial_runtime_contract.py",
    "tests/test_production_script.py",
    "tests/test_e2e_orchestration.py",
    "tests/test_e2e_failure_paths.py",
    "tests/test_editorial_regression_runtime.py",
]:
    text = read(path).replace("evidence_news_indices", "evidence_ids")
    # numeric beat refs become semantic default id in simple fixtures
    text = text.replace('"evidence_ids": [1]', '"evidence_ids": ["case"]')
    text = text.replace('"evidence_ids": [2, 5]', '"evidence_ids": ["case-a", "case-b"]')
    text = text.replace('"evidence_ids": [2]', '"evidence_ids": ["case-b"]')
    text = text.replace('"evidence_ids": []', '"evidence_ids": []')
    # common evidence fixtures
    text = text.replace(
        '"selected_news_index": 1, "role": "anchor", "argument_role": "evidence",',
        '"evidence_id": "case", "selected_news_index": 1, "role": "anchor", "argument_role": "evidence",',
    )
    text = text.replace(
        '"selected_news_index": 1,\n                                "role": "anchor",',
        '"evidence_id": "case",\n                                "selected_news_index": 1,\n                                "role": "anchor",',
    )
    write(path, text)

# Production test has two selected evidence items defined only through beats; add explicit evidence catalog where needed.
path = "tests/test_production_script.py"
text = read(path)
# For the large fixture, inject evidence before beats if missing.
needle = '        "beats": [\n            {\n                    "beat_id": "first-reveal",'
if needle in text and '"evidence": [' not in text.split(needle)[0][-600:]:
    text = text.replace(
        needle,
        '        "evidence": [\n            {"evidence_id": "case-a", "selected_news_index": 1, "role": "anchor", "argument_role": "evidence", "narrative_function": "Primer caso"},\n            {"evidence_id": "case-b", "selected_news_index": 2, "role": "contrast", "argument_role": "counterexample", "narrative_function": "Segundo caso"}\n        ],\n' + needle,
        1,
    )
# Map the two beat refs precisely.
text = text.replace('"evidence_ids": [1],', '"evidence_ids": ["case-a"],')
text = text.replace('"evidence_ids": [2],', '"evidence_ids": ["case-b"],')
# Small alignment fixture needs evidence catalog.
text = text.replace(
    '        episode_plan = {\n            "hook": "hook",\n            "historical_mirror": "",\n            "beats": [{"beat_id": "case",',
    '        episode_plan = {\n            "hook": "hook",\n            "historical_mirror": "",\n            "evidence": [{"evidence_id": "case", "selected_news_index": 1}],\n            "beats": [{"beat_id": "case",',
    1,
)
write(path, text)

# Runtime contract: simple valid plan evidence id.
path = "tests/test_editorial_runtime_contract.py"
text = read(path)
text = text.replace(
    '        "evidence": [{\n            "selected_news_index": 1,',
    '        "evidence": [{\n            "evidence_id": "case",\n            "selected_news_index": 1,',
    1,
)
text = text.replace('self.assertEqual(plan.beats[0].evidence_ids, [1])', 'self.assertEqual(plan.beats[0].evidence_ids, ["case"])')
write(path, text)

# E2E failure simple plan evidence id if not already inserted.
path = "tests/test_e2e_failure_paths.py"
text = read(path)
text = text.replace(
    '        "evidence": [{\n            "selected_news_index": 1,',
    '        "evidence": [{\n            "evidence_id": "case",\n            "selected_news_index": 1,',
    1,
)
write(path, text)

# Script section unit test uses evidence IDs only as metadata; no catalog needed.
# Regression evaluator fixture needs catalog ID + matching beat ref.
path = "tests/test_editorial_regression_runtime.py"
text = read(path)
text = text.replace('"evidence": [{"selected_news_index": 1}]', '"evidence": [{"evidence_id": "case", "selected_news_index": 1}]')
write(path, text)

# Ensure no ambiguous field remains in product/tests.
for path in ["app/agent.py", "pipeline/run.py", "pipeline/script_sections.py", "pipeline/production_script.py"]:
    if "evidence_news_indices" in read(path):
        raise RuntimeError(f"ambiguous evidence_news_indices remains in {path}")

print("evidence-id migration applied")
