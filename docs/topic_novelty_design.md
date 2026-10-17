# Essay Novelty Memory — topic novelty and essay deduplication

AI News Daily must not publish the same editorial argument just because new headlines can support it.

**Essay Novelty Memory** is the conceptual name for the lightweight, approved-episode editorial-identity lookup already implemented through `previous_essays`. It is **not** another database, a new agent, or retrieval-augmented generation from full past scripts. The runtime field `previous_essays` and persisted artifact names stay unchanged for compatibility.

## Three distinct responsibilities

1. **Event deduplication** — `previous_selected_news` is derived from stories demonstrably covered by previously approved episodes. It prevents reusing the same underlying event without a material development.
2. **Essay-topic deduplication** — `previous_essays` contains recent approved essays' editorial identities, so new evidence does not accidentally produce the same central question or argument.
3. **Narrative Memory reuse** — `editorial/narrative_memory.jsonl` is a separate, verified library of external historical/scientific/structural parallels. Its own approval checks, usage history and cooldown determine which reusable parallels are offered.

These checks answer different questions: *Have we covered this event? Have we already made this argument? Have we recently used this external parallel?* They should not be merged into a single retrieval layer.

## Planning contract

The Editorial Director receives `previous_essays` as **context to avoid repetition**, not a knowledge source from which to build today's script. Before writing, the Director must produce:

- `topic_signature`: a concise semantic label for the essay's actual subject;
- `central_question` and `thesis`: its editorial argument;
- `narrative_lens`: the human/intellectual perspective;
- `novelty_angle`: a concrete reason this episode differs from approved predecessors;
- current-news evidence with independently verified provenance.

New companies, model names, or benchmarks do not by themselves make an old argument novel. Revisiting a topic is valid when new evidence materially changes the question, thesis, mechanism, or human stakes.

## Runtime lookup and boundaries

`pipeline/run.py` uses `load_essay_history()` to read previously approved **modern** `episode_plan.json` artifacts, bounded by `ESSAY_HISTORY_DAYS` (default 120) and `MAX_RECENT_ESSAYS` (default 12). The recorded identity includes the question, thesis, lens, topic signature, mechanism, used evidence keys and primary Narrative Memory ID.

The history payload currently also carries an optional hook and up to 1,600 characters of `script_excerpt` for Director context; **neither is part of the blocking comparison**. They are not authoritative factual evidence and must not be used to copy earlier wording. Full past scripts are not required by the novelty gate.

News facts for the new episode come from the current discovery/evidence contract, not from `previous_essays` or from previous scripts.

## Deterministic guardrail (multidimensional v2)

`pipeline/core.py::assess_episode_novelty()` evaluates a proposed plan against prior editorial identities **before** the Writer runs. Its aggregate retrieval similarity finds the nearest comparator and supports diagnostics; that score **alone never blocks an episode**.

The gate blocks only when multiple relevant dimensions align, such as:

- the same causal/argumentative mechanism **and** a substantially matching question or thesis;
- a substantially matching central question **and** thesis;
- significant overlap in previously used source evidence **plus** a matching editorial argument.

A repeated broad theme, generic vocabulary, or the same Narrative Memory ID alone is not enough. A duplicate triggers bounded replanning with explicit feedback. If no distinct angle can be found, production returns non-fatal `no_novel_essay_angle` and publishes nothing.

The run stores its decision and diagnostics in `novelty_check.json`; changing this conceptual label does not change any runtime key, schema, workflow, gate or threshold.

## Why not solve this with temperature?

Higher temperature can vary wording but does not guarantee a new underlying argument, and may make factual narration less stable. Diversity should come from distinct editorial questions and evidence, with a deterministic novelty check rather than a stylistic randomness setting.
