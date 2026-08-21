from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}: {old[:120]!r}")
    write(path, text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = read(path)
    start_i = text.index(start)
    end_i = text.index(end, start_i)
    write(path, text[:start_i] + replacement + text[end_i:])


# ALTO 3 — novelty scoring: generic single-concept overlap must not dominate.
core = read("pipeline/core.py")
insert_marker = "}\n\n\ndef _fold_text(value: str) -> str:"
weights = '''}\n\n_TOPIC_CONCEPT_WEIGHTS: dict[str, float] = {\n    "agency": 1.10,\n    "verification": 1.40,\n    "governance": 1.20,\n    "tools": 0.80,\n    "science": 1.00,\n    "security": 1.00,\n    "cognition": 0.80,\n    "learning": 0.65,\n    "work": 0.55,\n    "trust": 0.55,\n    "power": 0.80,\n    "privacy": 0.90,\n    "creativity": 0.70,\n}\n\n\ndef _fold_text(value: str) -> str:'''
if core.count(insert_marker) != 1:
    raise RuntimeError("pipeline/core.py: concept-weight insertion marker changed")
core = core.replace(insert_marker, weights, 1)
write("pipeline/core.py", core)

new_similarity = '''def _weighted_concept_similarity(left: set[str], right: set[str]) -> float:\n    shared = left & right\n    if not shared:\n        return 0.0\n    shared_weight = sum(_TOPIC_CONCEPT_WEIGHTS.get(item, 1.0) for item in shared)\n    left_weight = sum(_TOPIC_CONCEPT_WEIGHTS.get(item, 1.0) for item in left)\n    right_weight = sum(_TOPIC_CONCEPT_WEIGHTS.get(item, 1.0) for item in right)\n    union_weight = sum(_TOPIC_CONCEPT_WEIGHTS.get(item, 1.0) for item in (left | right))\n    containment = shared_weight / min(left_weight, right_weight)\n    jaccard = shared_weight / union_weight if union_weight else 0.0\n    raw = (0.65 * containment) + (0.35 * jaccard)\n    # One broad concept such as work/trust/learning is context, not enough evidence of a duplicate.\n    evidence_factor = min(1.0, len(shared) / 2.0)\n    return raw * evidence_factor\n\n\ndef topic_similarity(left: str, right: str) -> float:\n    a = normalize_topic_text(left)\n    b = normalize_topic_text(right)\n    if not a or not b:\n        return 0.0\n\n    a_roots = _topic_roots(left)\n    b_roots = _topic_roots(right)\n    if not a_roots or not b_roots:\n        return 0.0\n\n    lexical_set_score = _set_similarity(a_roots, b_roots)\n    sequence = SequenceMatcher(\n        None, " ".join(sorted(a_roots)), " ".join(sorted(b_roots))\n    ).ratio()\n    lexical_score = (0.85 * lexical_set_score) + (0.15 * sequence)\n\n    left_concepts = topic_concepts(left)\n    right_concepts = topic_concepts(right)\n    shared_concepts = left_concepts & right_concepts\n    concept_score = _weighted_concept_similarity(left_concepts, right_concepts)\n\n    # Semantic families become strong evidence only when at least two independent concepts agree.\n    # Otherwise lexical similarity carries most of the decision, reducing false positives.\n    if len(shared_concepts) >= 2:\n        score = (0.40 * lexical_score) + (0.60 * concept_score)\n    else:\n        score = (0.80 * lexical_score) + (0.20 * concept_score)\n    return round(score, 4)\n\n\n'''
replace_between("pipeline/core.py", "def topic_similarity(left: str, right: str) -> float:\n", "def nearest_essay_similarity(\n", new_similarity)

# ALTO 9 — deterministic source parsing and provenance.
write("pipeline/news.py", '''from __future__ import annotations\n\nimport re\nfrom pathlib import Path\nfrom typing import Literal\nfrom urllib.parse import urlparse\n\nfrom pydantic import BaseModel, Field\n\n\nclass NewsItem(BaseModel):\n    news_id: str\n    source_file: str\n    source_locator: str\n    item_index: int = Field(ge=1)\n    title: str\n    date: str\n    date_origin: Literal["field", "source_file"]\n    source: str\n    url: str = ""\n    url_quality: Literal["article", "generic", "missing"]\n    category: str = ""\n    summary: str = ""\n    why_it_matters: str = ""\n    raw_content: str\n\n\ndef classify_url(url: str) -> Literal["article", "generic", "missing"]:\n    value = str(url or "").strip()\n    if not value:\n        return "missing"\n    parsed = urlparse(value)\n    if parsed.scheme not in {"http", "https"} or not parsed.netloc:\n        return "missing"\n    path = parsed.path.rstrip("/").lower()\n    generic_suffixes = (\n        "",\n        "/blog",\n        "/news",\n        "/announcements",\n        "/blog-category/announcements",\n        "/press",\n        "/updates",\n    )\n    if path in generic_suffixes or "/blog-category/" in path:\n        return "generic"\n    return "article"\n\n\ndef _field(block: str, label: str) -> str:\n    match = re.search(rf"(?mi)^{re.escape(label)}\\s*:\\s*(.+?)\\s*$", block)\n    return match.group(1).strip() if match else ""\n\n\ndef parse_news_file(path: Path) -> list[NewsItem]:\n    text = path.read_text(encoding="utf-8").strip()\n    if not text:\n        return []\n    matches = list(re.finditer(r"(?m)^##\\s+(\\d+)\\.\\s+(.+?)\\s*$", text))\n    if not matches:\n        raise ValueError(f"No structured '## N. title' news items found in {path}")\n\n    file_date = path.stem if re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", path.stem) else ""\n    items: list[NewsItem] = []\n    for position, match in enumerate(matches):\n        item_index = int(match.group(1))\n        start = match.start()\n        end = matches[position + 1].start() if position + 1 < len(matches) else len(text)\n        block = text[start:end].strip()\n        title = match.group(2).strip()\n        explicit_date = _field(block, "Fecha")\n        date_value = explicit_date or file_date\n        date_origin: Literal["field", "source_file"] = "field" if explicit_date else "source_file"\n        url = _field(block, "Enlace")\n        source_file = path.name\n        items.append(\n            NewsItem(\n                news_id=f"{path.stem}:{item_index}",\n                source_file=source_file,\n                source_locator=f"{source_file}#item-{item_index}",\n                item_index=item_index,\n                title=title,\n                date=date_value,\n                date_origin=date_origin,\n                source=_field(block, "Fuente"),\n                url=url,\n                url_quality=classify_url(url),\n                category=_field(block, "Categoría"),\n                summary=_field(block, "Resumen"),\n                why_it_matters=_field(block, "Por qué importa"),\n                raw_content=block,\n            )\n        )\n    return items\n''')

# ALTO 6 — exact narrative section alignment via internal writer markers.
write("pipeline/script_sections.py", '''from __future__ import annotations\n\nimport re\nfrom typing import Any\n\n\nMARKER_RE = re.compile(r"<!--SECTION:(opening|synthesis|story:\\d+)-->")\n\n\nclass SectionAlignmentError(ValueError):\n    pass\n\n\ndef expected_section_keys(episode_plan: dict[str, Any]) -> list[str]:\n    stories = episode_plan.get("stories", []) if isinstance(episode_plan, dict) else []\n    keys = ["opening"]\n    for story in stories:\n        if not isinstance(story, dict):\n            continue\n        index = int(story.get("selected_news_index", 0) or 0)\n        if index < 1:\n            raise SectionAlignmentError("episode_plan contains an invalid selected_news_index")\n        keys.append(f"story:{index}")\n    keys.append("synthesis")\n    return keys\n\n\ndef parse_sectioned_script(value: str, episode_plan: dict[str, Any]) -> tuple[str, dict[str, Any]]:\n    text = str(value or "").strip()\n    matches = list(MARKER_RE.finditer(text))\n    expected = expected_section_keys(episode_plan)\n    if not matches:\n        raise SectionAlignmentError("Writer returned no internal section markers")\n    if text[: matches[0].start()].strip():\n        raise SectionAlignmentError("Narration appeared before the opening section marker")\n    keys = [match.group(1) for match in matches]\n    if keys != expected:\n        raise SectionAlignmentError(f"Section markers must be exactly {expected}; got {keys}")\n\n    sections: list[dict[str, Any]] = []\n    clean_parts: list[str] = []\n    for index, match in enumerate(matches):\n        start = match.end()\n        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)\n        spoken = text[start:end].strip()\n        if not spoken:\n            raise SectionAlignmentError(f"Section {match.group(1)} is empty")\n        if MARKER_RE.search(spoken):\n            raise SectionAlignmentError("Nested section marker detected")\n        key = match.group(1)\n        section: dict[str, Any] = {\n            "section_key": key,\n            "kind": "opening" if key == "opening" else "synthesis" if key == "synthesis" else "development",\n            "selected_news_index": int(key.split(":", 1)[1]) if key.startswith("story:") else None,\n            "spoken_text": spoken,\n            "word_count": len(spoken.split()),\n        }\n        sections.append(section)\n        clean_parts.append(spoken)\n\n    clean_script = "\\n\\n".join(clean_parts).strip()\n    return clean_script, {"schema_version": 1, "sections": sections}\n''')

# Agent selector becomes ID-only; Writer/Refiner preserve hidden section markers.
agent = read("app/agent.py")
old_selection = '''class SelectionResult(BaseModel):\n    items: List[SelectedNewsItem] = Field(default_factory=list, max_length=CONFIG.max_selected_news)\n    discarded_duplicates: List[str] = Field(default_factory=list)\n    selection_notes: List[str] = Field(default_factory=list)\n'''
new_selection = '''class SelectedNewsRef(BaseModel):\n    news_id: str = Field(min_length=3, max_length=160)\n    selection_reason: str = ""\n\n\nclass SelectionResult(BaseModel):\n    items: List[SelectedNewsRef] = Field(default_factory=list, max_length=CONFIG.max_selected_news)\n    discarded_duplicates: List[str] = Field(default_factory=list)\n    selection_notes: List[str] = Field(default_factory=list)\n'''
if agent.count(old_selection) != 1:
    raise RuntimeError("app/agent.py: SelectionResult contract changed")
agent = agent.replace(old_selection, new_selection, 1)
agent = agent.replace(
    "- Preserve factual date, source, and URL when present.\n- Rank by potential value as ESSAY EVIDENCE, strongest first.\n- Never invent facts that are not supported by source material.\n",
    "- The source catalog already owns title/date/source/URL provenance. Return ONLY news_id + selection_reason for each chosen item; never reconstruct metadata.\n- Treat url_quality=generic or missing as weaker provenance. Never upgrade or invent a more specific URL.\n- Rank by potential value as ESSAY EVIDENCE, strongest first.\n- Never invent facts that are not supported by source material.\n",
    1,
)
marker_anchor = "HOW NEWS ENTERS:\n"
marker_text = '''INTERNAL SECTION ALIGNMENT — REQUIRED BUT NEVER SPOKEN:\n- Return the draft with HTML-comment markers that Python will remove before judges/TTS.\n- Exact order: <!--SECTION:opening-->, then one <!--SECTION:story:N--> for EACH episode_plan.stories item in plan order using its selected_news_index, then <!--SECTION:synthesis-->.\n- Put each marker immediately before the narration belonging to that block.\n- Do not add any other SECTION markers. Do not wrap the result in a code fence.\n- These markers are metadata, not headings; narration must flow naturally across them.\n- Do NOT include a subscribe/comment CTA in the raw essay; the deterministic production layer appends the CTA after the reflective closing question.\n\n'''
if agent.count(marker_anchor) < 1:
    raise RuntimeError("app/agent.py: writer HOW NEWS ENTERS marker not found")
writer_pos = agent.index(marker_anchor, agent.index("writer_agent = Agent("))
agent = agent[:writer_pos] + marker_text + agent[writer_pos:]
agent = agent.replace(
    "- the ending earns its reflective question and CTA.\n",
    "- the ending earns its reflective question; the deterministic production layer handles the subscribe/comment CTA.\n",
    1,
)
agent = agent.replace(
    "Revise {{draft_script}} using {{review}}, {{seo_review}}, {{attention_review}}, and {{voice_review}}.\n",
    "Revise {{sectioned_draft_script}} using {{review}}, {{seo_review}}, {{attention_review}}, and {{voice_review}}.\n",
    1,
)
agent = agent.replace(
    "Never expose internal dramaturgical labels in narration.\n",
    "Never expose internal dramaturgical labels in narration. Preserve the exact hidden HTML markers <!--SECTION:opening-->, <!--SECTION:story:N-->, and <!--SECTION:synthesis--> in the same order; return them with the revised draft so Python can align production sections. Do not add a subscribe/comment CTA; production adds it downstream.\n",
    1,
)
agent = agent.replace(
    "The news material is the factual source for current events. The curated historical references inside\n",
    "The news material is a structured factual source for current events. news_id/source_locator/url_quality are provenance metadata owned by Python; generic or missing URLs are weaker traceability and must never be treated as article-specific evidence. The curated historical references inside\n",
    1,
)
write("app/agent.py", agent)

# run.py: structured news catalog, deterministic selection materialization, section alignment, logical media paths.
run = read("pipeline/run.py")
run = run.replace("from pipeline.media import download_shot_asset\n", "from pipeline.media import download_shot_asset\nfrom pipeline.news import NewsItem, parse_news_file\nfrom pipeline.script_sections import SectionAlignmentError, parse_sectioned_script\n", 1)
new_collect = '''def collect_available_news(\n    news_dir: Path, target_date: date\n) -> tuple[str, list[Path], list[date], list[NewsItem]]:\n    available: list[Path] = []\n    missing: list[date] = []\n    items: list[NewsItem] = []\n    for news_date in expected_news_dates(target_date):\n        path = news_dir / f"{news_date.isoformat()}.txt"\n        if not path.exists() or not path.read_text(encoding="utf-8").strip():\n            missing.append(news_date)\n            continue\n        parsed = parse_news_file(path)\n        if not parsed:\n            raise ValueError(f"No structured news items parsed from {path}")\n        available.append(path)\n        items.extend(parsed)\n    payload = {\n        "schema_version": 1,\n        "items": [item.model_dump() for item in items],\n    }\n    return json.dumps(payload, ensure_ascii=False), available, missing, items\n\n\ndef materialize_selection(\n    decision: dict[str, Any], source_items: list[NewsItem]\n) -> dict[str, Any]:\n    catalog = {item.news_id: item for item in source_items}\n    selected: list[dict[str, Any]] = []\n    seen: set[str] = set()\n    for ref in decision.get("items", []) if isinstance(decision, dict) else []:\n        if not isinstance(ref, dict):\n            raise ValueError("Selector returned a non-object item reference")\n        news_id = str(ref.get("news_id", "") or "").strip()\n        if news_id not in catalog:\n            raise ValueError(f"Selector referenced unknown news_id={news_id!r}")\n        if news_id in seen:\n            raise ValueError(f"Selector referenced duplicate news_id={news_id!r}")\n        seen.add(news_id)\n        record = catalog[news_id].model_dump()\n        record["selection_reason"] = str(ref.get("selection_reason", "") or "").strip()\n        selected.append(record)\n    return {\n        "items": selected,\n        "discarded_duplicates": decision.get("discarded_duplicates", []),\n        "selection_notes": decision.get("selection_notes", []),\n    }\n\n\n'''
start = run.index("def collect_available_news(")
end = run.index("def load_selection_history(", start)
run = run[:start] + new_collect + run[end:]
run = run.replace(
    "news_text, available_files, missing_dates = collect_available_news(news_dir, target_date)\n        if not news_text:\n",
    "news_text, available_files, missing_dates, source_items = collect_available_news(news_dir, target_date)\n        if not source_items:\n",
    1,
)
old_sel = '''        selection = SelectionResult.model_validate(\n            selection_state.get("selected_news", {})\n        ).model_dump()\n        write_json(episode_scripts_dir / "selected_news.json", selection)\n'''
new_sel = '''        selection_decision = SelectionResult.model_validate(\n            selection_state.get("selected_news", {})\n        ).model_dump()\n        selection = materialize_selection(selection_decision, source_items)\n        write_json(episode_scripts_dir / "selected_news.json", selection)\n'''
if run.count(old_sel) != 1:
    raise RuntimeError("pipeline/run.py: selection block changed")
run = run.replace(old_sel, new_sel, 1)
old_writer = '''        draft_script = str(writer_state.get("draft_script", "")).strip()\n        if not draft_script:\n            raise RuntimeError("Writer did not produce draft_script")\n\n        final_editorial: dict[str, Any] = {}\n'''
new_writer = '''        sectioned_draft_script = str(writer_state.get("draft_script", "")).strip()\n        if not sectioned_draft_script:\n            raise RuntimeError("Writer did not produce draft_script")\n        try:\n            draft_script, script_alignment = parse_sectioned_script(\n                sectioned_draft_script, episode_plan\n            )\n        except SectionAlignmentError as exc:\n            raise RuntimeError(f"Writer section alignment invalid: {exc}") from exc\n\n        final_editorial: dict[str, Any] = {}\n'''
if run.count(old_writer) != 1:
    raise RuntimeError("pipeline/run.py: writer block changed")
run = run.replace(old_writer, new_writer, 1)
run = run.replace(
    '''                {\n                    **review_base,\n                    "review": json.dumps(final_editorial, ensure_ascii=False),\n''',
    '''                {\n                    **review_base,\n                    "sectioned_draft_script": sectioned_draft_script,\n                    "review": json.dumps(final_editorial, ensure_ascii=False),\n''',
    1,
)
old_refined = '''            refined = str(refiner_state.get("draft_script", "")).strip()\n            if not refined:\n                raise RuntimeError("Refiner did not produce draft_script")\n            draft_script = refined\n\n        (episode_scripts_dir / "script.txt").write_text(\n            draft_script + "\\n", encoding="utf-8"\n        )\n'''
new_refined = '''            refined = str(refiner_state.get("draft_script", "")).strip()\n            if not refined:\n                raise RuntimeError("Refiner did not produce draft_script")\n            try:\n                refined_script, refined_alignment = parse_sectioned_script(refined, episode_plan)\n            except SectionAlignmentError as exc:\n                validation_warnings.append(\n                    f"Refiner iteration {iteration} returned invalid section markers; kept previous valid draft: {exc}"\n                )\n                continue\n            sectioned_draft_script = refined\n            draft_script = refined_script\n            script_alignment = refined_alignment\n\n        (episode_scripts_dir / "script.txt").write_text(\n            draft_script + "\\n", encoding="utf-8"\n        )\n        write_json(episode_scripts_dir / "script_sections.json", script_alignment)\n'''
if run.count(old_refined) != 1:
    raise RuntimeError("pipeline/run.py: refiner/final-script block changed")
run = run.replace(old_refined, new_refined, 1)
old_media_call = '''                        destination,\n                    )\n'''
new_media_call = '''                        destination,\n                        logical_file=f"assets/{destination.name}",\n                    )\n'''
# Only replace the download_shot_asset call occurrence near the manifest.
media_call_pos = run.index("download_shot_asset(")
sub = run[media_call_pos:]
if sub.count(old_media_call) < 1:
    raise RuntimeError("pipeline/run.py: media call tail changed")
sub = sub.replace(old_media_call, new_media_call, 1)
run = run[:media_call_pos] + sub
write("pipeline/run.py", run)

# ALTO 4 — manifest stores episode-relative logical file paths.
media = read("pipeline/media.py")
media = media.replace(
    "def download_shot_asset(shot: dict[str, Any], destination: Path) -> dict[str, Any]:\n",
    "def download_shot_asset(\n    shot: dict[str, Any], destination: Path, *, logical_file: str | None = None\n) -> dict[str, Any]:\n",
    1,
)
media = media.replace('        "file": str(destination),\n', '        "file": logical_file or destination.name,\n', 1)
write("pipeline/media.py", media)

# ALTO 5 — logical artifact paths in run_report; hashes remain identity.
report = read("pipeline/report.py")
report = report.replace(
    '''def artifact_record(path: Path) -> dict[str, Any]:\n    return {\n        "path": str(path),\n''',
    '''def artifact_record(path: Path, logical_path: str) -> dict[str, Any]:\n    return {\n        "path": logical_path,\n''',
    1,
)
start = report.index("    artifacts = {\n")
end = report.index("\n\n    return {", start)
artifacts_block = '''    artifacts = {\n        "run_state": artifact_record(scripts_dir / "run_state.json", f"scripts/{episode}/run_state.json"),\n        "execution_trace": artifact_record(scripts_dir / "execution_trace.json", f"scripts/{episode}/execution_trace.json"),\n        "selected_news": artifact_record(scripts_dir / "selected_news.json", f"scripts/{episode}/selected_news.json"),\n        "episode_plan": artifact_record(scripts_dir / "episode_plan.json", f"scripts/{episode}/episode_plan.json"),\n        "novelty_check": artifact_record(scripts_dir / "novelty_check.json", f"scripts/{episode}/novelty_check.json"),\n        "reviews": artifact_record(scripts_dir / "reviews.json", f"scripts/{episode}/reviews.json"),\n        "script": artifact_record(scripts_dir / "script.txt", f"scripts/{episode}/script.txt"),\n        "script_sections": artifact_record(scripts_dir / "script_sections.json", f"scripts/{episode}/script_sections.json"),\n        "production_script_md": artifact_record(scripts_dir / "production_script.md", f"scripts/{episode}/production_script.md"),\n        "production_script_json": artifact_record(scripts_dir / "production_script.json", f"scripts/{episode}/production_script.json"),\n        "multimedia_plan": artifact_record(multimedia_dir / "plan.json", f"multimedia/{episode}/plan.json"),\n        "multimedia_manifest": artifact_record(multimedia_dir / "manifest.json", f"multimedia/{episode}/manifest.json"),\n        "voice_profile": artifact_record(editorial_dir / "voice_profile.md", "editorial/voice_profile.md"),\n        "discourse_profile": artifact_record(editorial_dir / "discourse_profile.md", "editorial/discourse_profile.md"),\n    }'''
report = report[:start] + artifacts_block + report[end:]
report = report.replace('        "schema_version": 5,\n', '        "schema_version": 6,\n', 1)
selection_anchor = '''        "selection": {\n            "selected_count": len(selected_items),\n'''
selection_replacement = '''        "selection": {\n            "selected_count": len(selected_items),\n            "provenance": {\n                "article_urls": sum(1 for item in selected_items if isinstance(item, dict) and item.get("url_quality") == "article"),\n                "generic_urls": sum(1 for item in selected_items if isinstance(item, dict) and item.get("url_quality") == "generic"),\n                "missing_urls": sum(1 for item in selected_items if isinstance(item, dict) and item.get("url_quality") == "missing"),\n                "source_locators": [item.get("source_locator", "") for item in selected_items if isinstance(item, dict)],\n            },\n'''
if report.count(selection_anchor) != 1:
    raise RuntimeError("pipeline/report.py: selection anchor changed")
report = report.replace(selection_anchor, selection_replacement, 1)
write("pipeline/report.py", report)

# ALTO 6 — production script consumes exact writer alignment; approved episodes fail closed without it.
prod = read("pipeline/production_script.py")
prod = prod.replace(
    '''        {\n            "kind": "opening",\n''',
    '''        {\n            "section_key": "opening",\n            "kind": "opening",\n''',
    1,
)
prod = prod.replace(
    '''            {\n                "kind": "development",\n''',
    '''            {\n                "section_key": f"story:{selected_index}",\n                "selected_news_index": selected_index,\n                "kind": "development",\n''',
    1,
)
prod = prod.replace(
    '''        {\n            "kind": "synthesis",\n''',
    '''        {\n            "section_key": "synthesis",\n            "kind": "synthesis",\n''',
    1,
)
insert_after = "    return sections\n\n\ndef media_cues_for_section(\n"
aligned_fn = '''    return sections\n\n\ndef allocate_aligned_narration(\n    body_text: str,\n    specs: list[dict[str, Any]],\n    alignment: dict[str, Any],\n    words_per_second: float,\n) -> list[dict[str, Any]]:\n    aligned = alignment.get("sections", []) if isinstance(alignment, dict) else []\n    if not aligned:\n        raise ValueError("script_sections.json has no sections")\n    spec_by_key = {str(spec.get("section_key", "")): spec for spec in specs}\n    keys = [str(item.get("section_key", "")) for item in aligned if isinstance(item, dict)]\n    if keys != list(spec_by_key):\n        raise ValueError(f"script section keys do not match episode plan: {keys} != {list(spec_by_key)}")\n    joined = " ".join(str(item.get("spoken_text", "") or "").strip() for item in aligned)\n    norm = lambda value: re.sub(r"\\s+", " ", value.strip())\n    if norm(joined) != norm(body_text):\n        raise ValueError("script_sections.json text does not match script.txt")\n\n    sections: list[dict[str, Any]] = []\n    cumulative_words = 0\n    for item in aligned:\n        key = str(item.get("section_key", ""))\n        spoken_text = str(item.get("spoken_text", "") or "").strip()\n        section_words = word_count(spoken_text)\n        start_seconds = math.ceil(cumulative_words / words_per_second) if cumulative_words else 0\n        cumulative_words += section_words\n        end_seconds = math.ceil(cumulative_words / words_per_second) if cumulative_words else start_seconds\n        sections.append(\n            {\n                **spec_by_key[key],\n                "spoken_text": spoken_text,\n                "word_count": section_words,\n                "start_seconds": start_seconds,\n                "end_seconds": max(start_seconds, end_seconds),\n                "duration_seconds": max(0, end_seconds - start_seconds),\n            }\n        )\n    return sections\n\n\ndef media_cues_for_section(\n'''
if prod.count(insert_after) != 1:
    raise RuntimeError("pipeline/production_script.py: allocate insertion anchor changed")
prod = prod.replace(insert_after, aligned_fn, 1)
prod = prod.replace(
    '''    media_plan: dict[str, Any],\n    words_per_second: float,\n) -> dict[str, Any]:\n''',
    '''    media_plan: dict[str, Any],\n    words_per_second: float,\n    script_alignment: dict[str, Any] | None = None,\n) -> dict[str, Any]:\n''',
    1,
)
prod = prod.replace(
    '''    specs = build_section_specs(episode_plan, selected_news, body_duration)\n    sections = allocate_narration(body_text, specs, words_per_second)\n''',
    '''    specs = build_section_specs(episode_plan, selected_news, body_duration)\n    if script_alignment and script_alignment.get("sections"):\n        sections = allocate_aligned_narration(body_text, specs, script_alignment, words_per_second)\n        alignment_mode = "writer_markers"\n    else:\n        sections = allocate_narration(body_text, specs, words_per_second)\n        alignment_mode = "proportional_fallback"\n''',
    1,
)
prod = prod.replace(
    '''        "multimedia_plan_available": bool(raw_segments),\n        "sections": sections,\n''',
    '''        "multimedia_plan_available": bool(raw_segments),\n        "alignment_mode": alignment_mode,\n        "sections": sections,\n''',
    1,
)
old_payload = '''    payload = build_production_payload(\n        target_date=target_date,\n        script=script,\n        episode_plan=read_json(episode_scripts / "episode_plan.json", {}),\n        selected_news=read_json(episode_scripts / "selected_news.json", {}),\n        media_plan=read_json(multimedia_root / target_date / "plan.json", {}),\n        words_per_second=words_per_second or CONFIG.words_per_second,\n    )\n'''
new_payload = '''    run_state = read_json(episode_scripts / "run_state.json", {})\n    alignment = read_json(episode_scripts / "script_sections.json", {})\n    approved = str(run_state.get("status", "") or "") == "approved"\n    if approved and not (isinstance(alignment, dict) and alignment.get("sections")):\n        raise RuntimeError("Approved episode is missing script_sections.json alignment")\n    try:\n        payload = build_production_payload(\n            target_date=target_date,\n            script=script,\n            episode_plan=read_json(episode_scripts / "episode_plan.json", {}),\n            selected_news=read_json(episode_scripts / "selected_news.json", {}),\n            media_plan=read_json(multimedia_root / target_date / "plan.json", {}),\n            words_per_second=words_per_second or CONFIG.words_per_second,\n            script_alignment=alignment,\n        )\n    except ValueError as exc:\n        if approved:\n            raise RuntimeError(f"Approved episode has invalid script section alignment: {exc}") from exc\n        payload = build_production_payload(\n            target_date=target_date,\n            script=script,\n            episode_plan=read_json(episode_scripts / "episode_plan.json", {}),\n            selected_news=read_json(episode_scripts / "selected_news.json", {}),\n            media_plan=read_json(multimedia_root / target_date / "plan.json", {}),\n            words_per_second=words_per_second or CONFIG.words_per_second,\n            script_alignment=None,\n        )\n        payload["alignment_warning"] = str(exc)\n'''
if prod.count(old_payload) != 1:
    raise RuntimeError("pipeline/production_script.py: create payload block changed")
prod = prod.replace(old_payload, new_payload, 1)
write("pipeline/production_script.py", prod)

# Focused regression tests.
core_tests = read("tests/test_core.py")
insert = '''\n    def test_topic_similarity_does_not_block_same_broad_work_concept(self) -> None:\n        left = "El futuro del trabajo cambia cuando asistentes de IA automatizan tareas administrativas."\n        right = "Los ilustradores discuten derechos de autor y estilos generados por IA en su trabajo creativo."\n        self.assertLess(topic_similarity(left, right), self.config.essay_duplicate_threshold)\n\n    def test_topic_similarity_does_not_block_same_broad_trust_word(self) -> None:\n        left = "¿Podemos confiar en un agente que modifica producción sin supervisión?"\n        right = "¿Qué significa la confianza emocional tras meses conversando con un compañero de IA?"\n        self.assertLess(topic_similarity(left, right), self.config.essay_duplicate_threshold)\n'''
needle = "    def test_nearest_essay_similarity_returns_best_match(self) -> None:\n"
if core_tests.count(needle) != 1:
    raise RuntimeError("tests/test_core.py insertion point changed")
core_tests = core_tests.replace(needle, insert + "\n" + needle, 1)
write("tests/test_core.py", core_tests)

write("tests/test_news_parser.py", '''from __future__ import annotations\n\nimport tempfile\nimport unittest\nfrom pathlib import Path\n\nfrom pipeline.news import parse_news_file\n\n\nclass NewsParserTests(unittest.TestCase):\n    def test_parser_owns_provenance_and_flags_generic_urls(self) -> None:\n        with tempfile.TemporaryDirectory() as tmp:\n            path = Path(tmp) / "2026-08-21.txt"\n            path.write_text(\n                "# Noticias\\n\\n## 1. Caso uno\\nFecha: 2026-08-20\\nFuente: Fuente A\\nEnlace: https://example.com/blog\\nCategoría: agentes\\nResumen: Resumen uno\\nPor qué importa: Importa uno\\n\\n## 2. Caso dos\\nFuente: Fuente B\\nEnlace: https://example.com/news/specific-story\\nResumen: Resumen dos\\nPor qué importa: Importa dos\\n",\n                encoding="utf-8",\n            )\n            items = parse_news_file(path)\n            self.assertEqual([item.news_id for item in items], ["2026-08-21:1", "2026-08-21:2"])\n            self.assertEqual(items[0].source_locator, "2026-08-21.txt#item-1")\n            self.assertEqual(items[0].url_quality, "generic")\n            self.assertEqual(items[1].url_quality, "article")\n            self.assertEqual(items[1].date, "2026-08-21")\n            self.assertEqual(items[1].date_origin, "source_file")\n\n    def test_unstructured_file_fails_closed(self) -> None:\n        with tempfile.TemporaryDirectory() as tmp:\n            path = Path(tmp) / "2026-08-21.txt"\n            path.write_text("Título: sin heading estructurado", encoding="utf-8")\n            with self.assertRaises(ValueError):\n                parse_news_file(path)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''')

write("tests/test_script_sections.py", '''from __future__ import annotations\n\nimport unittest\n\nfrom pipeline.script_sections import SectionAlignmentError, parse_sectioned_script\n\n\nPLAN = {"stories": [{"selected_news_index": 2}, {"selected_news_index": 5}]}\n\n\nclass ScriptSectionTests(unittest.TestCase):\n    def test_markers_create_exact_clean_alignment(self) -> None:\n        marked = (\n            "<!--SECTION:opening-->Inicio intrigante. "\n            "<!--SECTION:story:2-->Primer caso con evidencia. "\n            "<!--SECTION:story:5-->Segundo caso que complica la idea. "\n            "<!--SECTION:synthesis-->Cierre que transforma el inicio."\n        )\n        clean, payload = parse_sectioned_script(marked, PLAN)\n        self.assertNotIn("SECTION", clean)\n        self.assertEqual(\n            [item["section_key"] for item in payload["sections"]],\n            ["opening", "story:2", "story:5", "synthesis"],\n        )\n        self.assertIn("Segundo caso", payload["sections"][2]["spoken_text"])\n\n    def test_missing_story_marker_is_rejected(self) -> None:\n        marked = "<!--SECTION:opening-->Inicio. <!--SECTION:story:2-->Caso. <!--SECTION:synthesis-->Cierre."\n        with self.assertRaises(SectionAlignmentError):\n            parse_sectioned_script(marked, PLAN)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''')

write("tests/test_media_manifest.py", '''from __future__ import annotations\n\nimport tempfile\nimport unittest\nfrom pathlib import Path\nfrom unittest.mock import patch\n\nfrom pipeline.media import download_shot_asset\n\n\nclass MediaManifestTests(unittest.TestCase):\n    def test_manifest_uses_logical_episode_relative_file(self) -> None:\n        with tempfile.TemporaryDirectory() as tmp, patch("pipeline.media.search_pexels", return_value=None), patch("pipeline.media.search_wikimedia", return_value=None):\n            destination = Path(tmp) / ".pipeline-runs" / "x" / "assets" / "slot_001.jpg"\n            record = download_shot_asset(\n                {"shot_number": 1, "visual_query": "abstract verification", "on_screen_text": "Verificar"},\n                destination,\n                logical_file="assets/slot_001.jpg",\n            )\n            self.assertEqual(record["file"], "assets/slot_001.jpg")\n            self.assertTrue(destination.exists())\n\n\nif __name__ == "__main__":\n    unittest.main()\n''')

report_tests = read("tests/test_report.py")
anchor = '            self.assertTrue(report["artifacts"]["run_state"]["sha256"])\n'
replacement = anchor + '            self.assertEqual(report["schema_version"], 6)\n            self.assertEqual(report["artifacts"]["run_state"]["path"], "scripts/2026-08-21/run_state.json")\n            self.assertNotIn(".pipeline-runs", report["artifacts"]["run_state"]["path"])\n'
if report_tests.count(anchor) != 1:
    raise RuntimeError("tests/test_report.py assertion anchor changed")
report_tests = report_tests.replace(anchor, replacement, 1)
write("tests/test_report.py", report_tests)

prod_tests = read("tests/test_production_script.py")
# Add a focused build-payload alignment test before module main.
needle = "\n\nif __name__ == \"__main__\":\n"
align_test = '''\n    def test_writer_alignment_overrides_proportional_allocation(self) -> None:\n        from pipeline.production_script import build_production_payload\n\n        script = "Inicio corto. Caso muy concreto con varias palabras. Cierre final."\n        episode_plan = {\n            "hook": "hook",\n            "historical_mirror": "",\n            "stories": [{"selected_news_index": 1, "estimated_minutes": 4, "narrative_function": "Caso real", "argument_role": "evidence"}],\n            "final_synthesis": "síntesis",\n            "closing_question": "¿Qué cambia?",\n        }\n        selected = {"items": [{"title": "Fuente exacta"}]}\n        alignment = {"sections": [\n            {"section_key": "opening", "spoken_text": "Inicio corto."},\n            {"section_key": "story:1", "spoken_text": "Caso muy concreto con varias palabras."},\n            {"section_key": "synthesis", "spoken_text": "Cierre final."},\n        ]}\n        payload = build_production_payload(\n            target_date="2026-08-21", script=script, episode_plan=episode_plan, selected_news=selected,\n            media_plan={}, words_per_second=2.5, script_alignment=alignment\n        )\n        self.assertEqual(payload["alignment_mode"], "writer_markers")\n        self.assertEqual(payload["sections"][1]["spoken_text"], "Caso muy concreto con varias palabras.")\n        self.assertEqual(payload["sections"][1]["source_evidence"], "Fuente exacta")\n'''
if prod_tests.count(needle) != 1:
    raise RuntimeError("tests/test_production_script.py main marker changed")
prod_tests = prod_tests.replace(needle, "\n" + align_test + needle, 1)
write("tests/test_production_script.py", prod_tests)

# Update deterministic E2E fixture to structured news IDs and internal section markers.
e2e = read("tests/test_e2e_orchestration.py")
e2e = e2e.replace(
    '        script = " ".join(["noticia"] * 1050)\n',
    '        script = ("<!--SECTION:opening-->" + " ".join(["noticia"] * 250) + " <!--SECTION:story:1-->" + " ".join(["noticia"] * 600) + " <!--SECTION:synthesis-->" + " ".join(["noticia"] * 200))\n',
    1,
)
old_fake_item = '''                            {\n                                "title": "Noticia importante",\n                                "date": "2026-08-20",\n                                "source": "Fuente primaria",\n                                "url": "https://example.com/story",\n                                "summary": "Resumen verificable",\n                                "why_it_matters": "Impacto claro",\n                                "category": "educacion",\n                            }\n'''
new_fake_item = '''                            {\n                                "news_id": "2026-08-20:1",\n                                "selection_reason": "Evidencia útil para el ensayo",\n                            }\n'''
if e2e.count(old_fake_item) != 1:
    raise RuntimeError("tests/test_e2e_orchestration.py selector fixture changed")
e2e = e2e.replace(old_fake_item, new_fake_item, 1)
old_news_fixture = '''                "Título: Noticia importante\\nFuente: Fuente primaria\\nEnlace: https://example.com/story\\n",\n'''
new_news_fixture = '''                "# Noticias\\n\\n## 1. Noticia importante\\nFecha: 2026-08-20\\nFuente: Fuente primaria\\nEnlace: https://example.com/story\\nCategoría: educacion\\nResumen: Resumen verificable\\nPor qué importa: Impacto claro\\n",\n'''
if e2e.count(old_news_fixture) != 1:
    raise RuntimeError("tests/test_e2e_orchestration.py news fixture changed")
e2e = e2e.replace(old_news_fixture, new_news_fixture, 1)
e2e = e2e.replace(
    '            self.assertTrue(episode_plan["topic_signature"])\n',
    '            self.assertTrue(episode_plan["topic_signature"])\n            self.assertTrue((result / "script_sections.json").exists())\n            selected_payload = json.loads((result / "selected_news.json").read_text(encoding="utf-8"))\n            self.assertEqual(selected_payload["items"][0]["source_locator"], "2026-08-20.txt#item-1")\n            self.assertEqual(selected_payload["items"][0]["url"], "https://example.com/story")\n',
    1,
)
write("tests/test_e2e_orchestration.py", e2e)

# ALTO 7 is updated separately through the connector because Actions cannot commit workflow files.
print("High 3-6 and 9 patch applied")
