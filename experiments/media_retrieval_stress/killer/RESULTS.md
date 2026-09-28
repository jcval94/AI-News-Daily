# Killer experiment — observed results

Run: `killer-live-web-2026-09-28`

## Score

| Stage | Result |
|---|---:|
| Entity resolution | **5 / 5** |
| Exact discovery | **5 / 5** |
| Visual/context verification | **5 / 5** |
| Exact + automatically usable | **3 / 5** |
| Exact + reference-only | **2 / 5** |
| Wrong generic substitutions | **0** |
| Video scene offsets resolved | **1 / 1 video case requiring scouting** |

## Cases

| Killer case | Discovery | Usability | Final state |
|---|---|---|---|
| Time Wizard / El Mago del Tiempo | Exact official card record found | Copyrighted reference; no reusable licence established | `FOUND_EXACT_REFERENCE_ONLY` |
| Lake Nyos 1986 | Exact USGS documentary source found | Public Domain | `FOUND_EXACT_USABLE` |
| Plato | Exact museum/Commons bust found | CC BY-SA 3.0 | `FOUND_EXACT_USABLE` |
| AlphaFold interface | Exact EMBL-EBI interface/training image found | CC BY 4.0 training material | `FOUND_EXACT_USABLE` |
| iPhone 2007 keynote | Exact keynote + timestamped scenes found | Reuse licence not established | `FOUND_EXACT_REFERENCE_ONLY` |

## Most important finding

The experiment does **not** support the hypothesis that semantic understanding is the main bottleneck.

All five killer identities were resolved and exact references were found.

The dominant remaining failure surface is:

```text
exact identity
    ↓
exact reference exists
    ↓
visual target verified
    ↓
rights / automatic acquisition boundary
```

For commercial/historical video assets, `REFERENCE_ONLY` is a materially better result than either
`NOT_FOUND` or a generic stock substitution.

## Video finding

The 2007 iPhone case confirms that fixed `0–30 s` clipping is unsafe.

The scene scout recovered multiple exact intervals from the keynote:

- 00:41:48 — slide to unlock
- 00:42:20 — finger scrolling
- 00:59:28 — pinch on photos
- 01:13:35 — pinch/zoom in Google Maps

The retrieval architecture should therefore preserve the full source reference first and decide the clip
window only after scene evidence is available.

## Recommendation from this experiment

The next provider experiment should optimise **coverage of exact references**, not simply the number of
rights-cleared search hits.

A useful production-facing contract would expose:

```text
FOUND_EXACT_USABLE
FOUND_EXACT_REFERENCE_ONLY
FOUND_CONTEXTUAL
NOT_FOUND
AMBIGUOUS
```

and only `FOUND_EXACT_USABLE` should be eligible for automatic montage without another rights decision.
