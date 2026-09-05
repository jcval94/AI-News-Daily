# Social Signals input

This directory is the editorial input that precedes news selection.

The purpose of a social signal is to describe a recent, source-backed observation about people,
institutions, work, learning, behavior, incentives, trust, power, regulation, science, or another
social consequence connected to AI or technological change.

A signal is **not** a headline summary and should not contain an essay thesis.

## Daily catalog

Future production wiring will read `signals/YYYY-MM-DD.json`.

Recommended shape:

```json
{
  "generated_at": "2026-08-28T09:00:00-06:00",
  "signals": [
    {
      "signal_id": "oversight_speed_gap",
      "date": "2026-08-27",
      "source": "Primary or high-quality source",
      "url": "https://example.org/source",
      "observation": "A concrete, source-backed observation.",
      "domains": ["work", "trust"],
      "evidence_type": "survey"
    }
  ]
}
```

## Editorial contract

Prefer signals from surveys, papers, official statistics, regulation, adoption data, labor or
education patterns, institutional changes, and observable behavior.

The Tension Scout must be able to move through:

```text
OBSERVATION
  -> SOCIAL PROBLEM
  -> HUMAN TENSION
  -> CENTRAL MYSTERY
  -> SECOND-ORDER QUESTION
```

Current news remains in `news/` and will later be matched **after** a tension/question is chosen.
This foundation intentionally keeps `tension_scout_agent` independent from `news_text`.
