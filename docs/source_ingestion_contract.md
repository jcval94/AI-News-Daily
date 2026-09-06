# Daily source ingestion contract

Production accepts one structured editorial source per calendar day from `news/`.

Supported filenames:

- canonical: `YYYY-MM-DD.txt`
- append-only timestamped: `YYYY-MM-DD-HH-MM-SS.txt`

Resolution is deterministic:

1. a non-empty canonical file wins;
2. otherwise the latest non-empty timestamped file for that date wins;
3. during source-coverage preflight, the selected timestamped file is copied to a transient canonical `YYYY-MM-DD.txt` alias inside the Actions workspace so the existing runtime consumes the same source that preflight validated;
4. transient aliases are not promoted or committed back to the repository.

Supported structured item formats:

- numbered Markdown headings such as `## 1. Title`;
- legacy numbered headings such as `1) Title`;
- current daily-digest blocks beginning with `Título: ...` and containing at minimum `Fecha:` and `Fuente:`.

The parser owns provenance. A model must never infer a missing source identity or silently repair an unstructured source file.

If multiple timestamped files exist for the same day, lexical timestamp order selects the latest file. News IDs remain day-stable (`YYYY-MM-DD:<item_index>`) while `source_file` and `source_locator` preserve the actual timestamped file used.
