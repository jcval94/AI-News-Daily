# Killer multimedia retrieval experiment

This experiment deliberately separates four questions that used to be conflated:

1. **Entity Resolution** — what exact person/object/event/interface/scene does the narration mean?
2. **Exact Discovery** — can we locate an exact reference somewhere, independent of reuse rights?
3. **Visual Verification** — does the actual image/video/scene show the requested subject?
4. **Usability / Rights** — may the asset enter automated production, or is it reference-only?

## Final states

- `FOUND_EXACT_USABLE`
- `FOUND_EXACT_REFERENCE_ONLY`
- `FOUND_CONTEXTUAL`
- `NOT_FOUND`
- `AMBIGUOUS`

The crucial rule is:

> Failure at usability must never rewrite exact identity into a generic substitute.

An exact reference-only result is therefore considered a successful **discovery** and a failed
**automatic acquisition**, not a failed search.

## Killer set

- Time Wizard / El Mago del Tiempo
- 1986 Lake Nyos disaster
- Plato historical depiction
- AlphaFold Database interface
- 2007 iPhone keynote gesture demonstration

## Observed run

`results/2026-09-28-live-web.json` records the first evidence-backed run using real public web
sources. It is intentionally stored separately from synthetic fixtures.

The run is observational: it records sources discovered on the web and classifies them through the
four-stage contract. It does not download or redistribute copyrighted media.
