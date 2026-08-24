# Observed run journey

The **Proceso E2E** tab now has two complementary views:

1. **Living architecture** — what the system is designed to do, rendered from `pipeline/architecture_manifest.py`.
2. **Run real** — what the current episode actually did, reconstructed from persisted artifacts.

The observed journey reads:

- `run_state.json` for the authoritative terminal state and reason,
- `execution_trace.json` for agent attempts, retries, timing and token usage,
- `novelty_check.json` for novelty attempts and final similarity,
- `reviews.json` for whether the quality gate was reached,
- `selected_news.json` for selected-story count,
- `cost_snapshot.json` for per-step estimated model cost,
- multimedia `manifest.json` when available.

A missing refiner is shown as **NO REQUERIDO** once the run reached the quality gate; it is not silently omitted. Non-publishable terminal states remain first-class observable outcomes.
