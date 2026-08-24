# E2E architecture synchronization

The GitHub Pages **Proceso E2E** view must describe the runtime that actually exists on `main`.

Current non-negotiable teaching points:

- `episode_plan.json` contains a pre-writing Claim Ledger with exactly one entry per planned evidence item.
- Refinement routing is deterministic: factual repair first, voice repair second, secondary SEO/attention polish last.
- The three refiners are physically isolated agents with deliberately different state payloads.
- No model decides retry policy, publication, promotion, filesystem mutation, or which refinement phase runs next.
- Only `approved` is publishable.

This note exists as a compact review contract; the rendered Pages implementation lives in `pipeline/review_hub_v9.py`.
