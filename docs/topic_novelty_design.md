# Topic novelty and essay deduplication

AI News Daily should not publish the same essay thesis repeatedly just because the supporting news changed.

## Principle

Deduplicate at two levels:

1. **Event deduplication** — existing selection history prevents the same underlying news event from being reused without material change.
2. **Essay-topic deduplication** — recent approved essays provide a memory of their central question, thesis, narrative lens and topic signature.

The second layer is intentionally more important for a video-essay product.

## Planning contract

Before choosing evidence, the Editorial Director receives `previous_essays` and must produce:

- `topic_signature`: short semantic label for the essay's real subject;
- `narrative_lens`: the main human/intellectual lens used to investigate it;
- `novelty_angle`: why this essay is materially different from recent episodes;
- `central_question` and `thesis`;
- current news only as supporting evidence.

A new company, model or benchmark is **not** enough novelty if the central argument is effectively the same.

A topic may be revisited only when new evidence materially changes the question, conclusion, mechanism or human stakes.

## Deterministic guardrail

After planning, Python compares the new `topic_signature + central_question + thesis` against recent approved essays.

- Low similarity: continue normally.
- High similarity: re-plan with explicit feedback about the nearest prior essay.
- Still too similar after bounded re-plans: return a non-fatal `no_novel_essay_angle` state and publish nothing.

This guardrail is deliberately bounded and runs before the Writer to avoid wasting model calls.

## Why not solve this with temperature?

Higher temperature can increase surface variation, but it does not reliably prevent semantic repetition and may make factual narration less stable. Diversity should first come from memory, explicit novelty constraints and different argumentative lenses. Temperature can remain a later stylistic tuning knob if the configured model supports it reliably.
