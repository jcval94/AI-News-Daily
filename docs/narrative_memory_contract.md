# Narrative Memory contract

Narrative Memory is a persistent, verified library of reusable historical, scientific, economic, natural, strategic and behavioral parallels for reflective AI essays.

It is **not** a trivia feed and it is **not** a second news source.

## Separation of responsibilities

```text
Scheduled research task
    ↓ discovers / verifies / enriches
editorial/narrative_memory.jsonl
    ↓ deterministic validation + retrieval
Editorial Director
    ↓ MUST select 1–2; one owns the opening hook
episode_plan.narrative_parallels
    ↓ exact selected records only
Writer + factual critic/refiner
    ↓
approved episode
    ↓
usage is derived from approved episode plans
```

The scheduled task may expand the library. Production remains authoritative about validation, retrieval, cooldown, selection bounds and publication.

## Core rule

A memory item exists only when it is both:

1. sufficiently verified to be treated as factual context; and
2. useful because it exposes a transferable mechanism, not merely because it is surprising.

Interestingness and usefulness are separate dimensions.

## JSONL schema

The canonical store is `editorial/narrative_memory.jsonl`, one JSON object per line.

Required fields:

- `id`: stable lowercase identifier.
- `title`, `one_liner`, `summary`.
- `verified_claims`: atomic claims safe to paraphrase as fact.
- `uncertainties`: limits, disputed details or missing evidence.
- `sources`: source URLs used to verify the record.
- `period`, `location`, `domains`.
- `mechanisms`: transferable structures such as `agility_vs_scale` or `technology_before_ecosystem`.
- `useful_for`: concepts the case can illuminate.
- `analogy_mapping`: what structural mapping is legitimate.
- `analogy_limits`: where the analogy breaks.
- `surprise_score`, `explanatory_score`, `analogy_potential`, `visual_score`, `sourceability_score`, `source_quality_score`, `confidence`: 0–10.
- `semantic_duplicate_risk`: `low|medium|high`.
- `source_kind`: `scheduled_research|editorial_seed`.
- `created_at`.
- `status`: normally `approved`.

## Deterministic admission gate

Production consumes only records satisfying:

```text
status == approved
surprise_score >= 8
explanatory_score >= 7
analogy_potential >= 7
source_quality_score >= 8
semantic_duplicate_risk == low
verified_claims != []
sources != []
```

Malformed or sub-threshold rows are quarantined from runtime context and surfaced as warnings. Narrative Memory is now a required editorial input: a production episode must have at least one valid retrieved record available for the Director.

## Retrieval

Retrieval is intentionally cheap and deterministic in v1.

It combines:

- lexical relevance to the selected-news context;
- editorial quality scores;
- a usage penalty;
- a 90-day default soft cooldown;
- greedy diversity over the primary mechanism.

The cooldown is a preference, not an absolute veto. Candidates outside cooldown rank first. If the library is temporarily exhausted, recently used candidates remain eligible with a strong penalty so the mandatory opening contract can still be satisfied.

Only a small candidate set reaches the Editorial Director. The full library never enters model context.

The Director must select **one or two** records. Exactly one selected record is also named by `episode_plan.opening_memory_id` and must carry the opening hook. A second record is optional and should be used only when it explains a different dimension.

## Factual boundary

The Writer and factual repair/judge receive only records explicitly selected by the Director. The Writer must develop the `opening_memory_id` record as a genuine opening micro-story, not a decorative mention.

They may paraphrase `verified_claims`. They must preserve `uncertainties` and `analogy_limits`. They may not invent precision beyond the record or silently turn a structural analogy into a causal equivalence.

Current-event facts still come from `news_text` / Claim Ledger. Narrative Memory never overrides current source evidence.

## Usage and anti-repetition

No mutable `used=true` flag is stored in the library.

Usage is derived from approved historical episode artifacts:

```text
scripts/<date>/episode_plan.json
    narrative_parallels[].memory_id
```

This produces `times_used`, `last_used_at` and `episodes_used` without creating a second mutable source of truth. Rejected or failed episodes do not count as usage.

## Scheduled-task write discipline

The daily scheduled research task should:

1. read this contract and the current JSONL library;
2. explore broadly and filter aggressively;
3. verify only finalists with high-quality sources;
4. reject semantic duplicates;
5. append only gate-passing records;
6. never modify or delete existing rows;
7. never edit scripts or episode artifacts.

The production loader revalidates everything even when the scheduled task claims a record passed.


## Opening-use contract

Narrative Memory is not satisfied by mentioning a title or dropping a historical fact into the middle of the essay.

For every publishable episode:

1. `episode_plan.narrative_parallels` contains 1–2 retrieved records.
2. `episode_plan.opening_memory_id` points to one of those records.
3. The Writer places `<!--MEMORY:<opening_memory_id>-->` inside the opening section within the first 120 spoken words, immediately before the narration grounded in that case.
4. The parser removes the marker from spoken output and fails alignment if it is missing, duplicated, points to another ID, or appears too late.
5. Editorial and Voice/Humanity judges must reject a script that name-drops the case without explaining the transferable mechanism or that violates its analogy limits.

The preferred opening shape is:

```text
verified micro-story
    ↓
surprising mechanism
    ↓
human tension
    ↓
central question
    ↓
provisional thesis
    ↓
current news as evidence
```
