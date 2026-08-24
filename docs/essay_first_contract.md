# Essay-first editorial contract

This document makes the essay-first principle explicit and reviewable.

The episode is not organized around headlines. The episode is organized around an idea **that changes while we investigate it**.

The north star remains:

> The essay is the product. The news is evidence.

## Required planning sequence

1. Human observation or intriguing image — something recognizable, strange, or counterintuitive.
2. Deeper tension — why that observation is not trivial.
3. Central mystery — what we genuinely do not understand yet.
4. Historical mirror — a verified precedent that changes how the present is understood when useful.
5. Provisional thesis — the narrator's current reading, intentionally incomplete.
6. Concrete scene — a real, historical, or clearly hypothetical situation that makes the abstraction visible.
7. Evidence strategy — which recent developments can test, support, complicate, or limit the thesis.
8. Claim Ledger — establish the factual boundary for every chosen current-news evidence item before prose is written.
9. First reveal — what the first strong evidence changes.
10. Narrative turn — the moment the deeper problem becomes different from the apparent initial problem.
11. Evolved thesis — the conclusion must be richer than a paraphrase of the provisional thesis.
12. Final payoff — return to an opening image, phrase, mystery, or motif with a changed meaning.
13. Synthesis — return to the human question, not to a recap of headlines.

The existing `EpisodePlan.narrative_arc` is the structured place to encode these dramaturgical beats. They are planning metadata, not spoken section labels.

## Claim Ledger contract

Every item in `EpisodePlan.evidence` must have exactly one `claim_ledger` entry with the same `evidence_id` and `selected_news_index`.

The ledger is created before the writer and contains:

- `supported_facts`: atomic source-backed claims safe to state as facts;
- `allowed_interpretations`: readings that are acceptable only when framed as the narrator's interpretation;
- `hypotheses`: plausible possibilities that must remain hypothetical;
- `uncertainties`: material things the source does not establish;
- `prohibited_claims`: tempting extrapolations the essay must not make from that evidence;
- `source_limitations`: provenance/detail limits that affect confidence.

The ledger is a factual boundary, not another narrative outline. `news_text` remains the ultimate source of truth if a ledger entry ever conflicts with the source.

Company marketing must not silently become a verified result. If the source only establishes that a company claims something, the safe fact is that **the company claims it**.

## Refinement separation

Refinement uses mutually exclusive responsibilities. One pass must not try to make a script safer and more stylish at the same time.

1. **Factual repair first.** When factuality/traceability is not already passing, only factual repairs are allowed: attribution, uncertainty, claim downgrades, unsupported-claim removal, and necessary precision edits. Voice/SEO/retention feedback waits.
2. **Voice repair second.** Only after factuality is low-risk and editorially passing may the refiner change cadence, sentence length, symmetry, transitions, conversational phrasing, and other AI-smell issues. The semantic claim set is frozen.
3. **Secondary polish last.** Attention or SEO edits are allowed only after both factual and voice gates pass, and they must not change claim semantics.

This ordering is designed to prevent the previous oscillation where a factual repair made the prose robotic and a later voice repair reintroduced unsupported implications.

## Intrigue contract

An opening may start from something extremely intriguing when the material earns it. Valid mechanisms include:

- an unexplained concrete scene;
- a counterintuitive claim that can be supported or qualified;
- a disturbing or difficult question;
- a strange but verified historical fact;
- two true facts that seem incompatible;
- a recurring image or phrase whose meaning will change;
- a clearly labeled hypothetical or future scene.

Intrigue must never become dishonest clickbait. The viewer should understand the core mystery roughly within the first minute, and every major open loop must receive a real payoff.

## Movement requirement

Reject an essay that simply behaves like:

`thesis → evidence 1 → same thesis → evidence 2 → same thesis → evidence 3 → conclusion`

Prefer:

`opening belief → mystery → evidence → first reveal → complication → narrative turn → second reveal → evolved thesis → payoff`

The key test is:

> If the exact conclusion is obvious after minute 2, the arc is still too flat.

## Recurring motif

When natural, choose one phrase, object, image, or question that appears 2–4 times and changes meaning. It should not behave like a slogan.

A strong payoff lets the final appearance reinterpret the first one.

## News roles

A current story may serve one of six argument roles:

- `evidence`: directly supports the thesis.
- `counterexample`: complicates or challenges it.
- `symptom`: reveals the broader pattern without proving it.
- `consequence`: shows what the underlying change produces.
- `limit_case`: reveals where the thesis stops working.
- `bridge`: connects two ideas without becoming the subject itself.

## Failure modes

Reject a plan or script that behaves like:

`headline → explanation → reflection → next headline`

Reject spoken structures such as:

- “Evidencia 1 / Evidencia 2 / Evidencia 3”;
- “Ahora veamos la segunda noticia”;
- mechanically repeated mini-conclusions;
- a conclusion that merely restates the opening thesis.

Reject openings that default to:

- “Hoy salió una noticia…”
- company/model/product names before the human idea is clear;
- benchmark names or jargon before explaining why the viewer should care.

The news may appear early when useful, but it must not become the organizing principle of the essay.
