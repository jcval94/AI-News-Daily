from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from pipeline.narrative_memory import NarrativeMemoryItem, gate_reasons

TZ = ZoneInfo("America/Mexico_City")
STAMP = r"(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2})"
TITLE_RE = re.compile(rf"^NARRATIVE_MEMORY_STAGING — {STAMP} America/Mexico_City$")
HEADER_RE = re.compile(rf"^# Narrative Memory Staging — {STAMP} America/Mexico_City$")
MAX_RECORDS = 4
NEAR_DUPLICATE_JACCARD = 0.82


def _write_output(name: str, value: str) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9áéíóúüñ]{4,}", value.casefold()))


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(
        [
            str(record.get("title", "")),
            str(record.get("one_liner", "")),
            str(record.get("summary", "")),
            " ".join(record.get("mechanisms", []) or []),
            " ".join(record.get("useful_for", []) or []),
        ]
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _valid_source(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _read_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"canonical store missing: {path}")
    records: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"existing JSONL invalid at line {line_no}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"existing JSONL line {line_no} is not an object")
        records.append(value)
    return records


def _parse_body(body: str, expected_header: str) -> list[dict[str, Any]]:
    lines = body.strip().splitlines()
    if not lines or lines[0].strip() != expected_header:
        raise ValueError("timestamp del título y encabezado no coincide")
    if not HEADER_RE.fullmatch(lines[0].strip()):
        raise ValueError("encabezado de staging no canónico")

    payload_lines = [line.strip() for line in lines[1:] if line.strip()]
    if not 1 <= len(payload_lines) <= MAX_RECORDS:
        raise ValueError(f"se requieren entre 1 y {MAX_RECORDS} registros JSONL; recibidos: {len(payload_lines)}")

    records: list[dict[str, Any]] = []
    for index, raw in enumerate(payload_lines, start=1):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"registro {index}: JSON inválido: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"registro {index}: debe ser un objeto JSON")
        records.append(value)
    return records


def _validate_records(
    incoming: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    issue_date: str,
) -> tuple[list[NarrativeMemoryItem], list[str]]:
    existing_by_id = {
        str(item.get("id", "")).strip(): item
        for item in existing
        if str(item.get("id", "")).strip()
    }
    existing_title = {
        str(item.get("title", "")).strip().casefold(): str(item.get("id", "")).strip()
        for item in existing
        if str(item.get("title", "")).strip()
    }
    existing_vectors = [
        (str(item.get("id", "")).strip(), _tokens(_record_text(item)))
        for item in existing
        if str(item.get("id", "")).strip()
    ]

    seen_ids: set[str] = set()
    validated: list[NarrativeMemoryItem] = []
    already_present: list[str] = []

    for index, raw in enumerate(incoming, start=1):
        try:
            item = NarrativeMemoryItem.model_validate(raw)
        except Exception as exc:
            raise ValueError(f"registro {index}: schema inválido: {exc}") from exc

        if item.id in seen_ids:
            raise ValueError(f"registro {index}: id duplicado dentro del staging: {item.id}")
        seen_ids.add(item.id)

        reasons = gate_reasons(item)
        if reasons:
            raise ValueError(f"registro {index} ({item.id}): no pasa gate: {','.join(reasons)}")
        if item.source_kind != "scheduled_research":
            raise ValueError(f"registro {index} ({item.id}): source_kind debe ser scheduled_research")
        if item.status != "approved":
            raise ValueError(f"registro {index} ({item.id}): status debe ser approved")
        if item.created_at != issue_date:
            raise ValueError(
                f"registro {index} ({item.id}): created_at={item.created_at!r}; esperado {issue_date!r}"
            )
        if not all(_valid_source(url) for url in item.sources):
            raise ValueError(f"registro {index} ({item.id}): sources contiene URL no http(s) válida")
        if len(set(item.sources)) != len(item.sources):
            raise ValueError(f"registro {index} ({item.id}): sources contiene duplicados")

        normalized = item.model_dump(mode="json")
        if item.id in existing_by_id:
            if _canonical(existing_by_id[item.id]) == _canonical(normalized):
                already_present.append(item.id)
                continue
            raise ValueError(f"registro {index}: id existente con contenido diferente: {item.id}")

        title_key = item.title.strip().casefold()
        if title_key in existing_title:
            raise ValueError(
                f"registro {index} ({item.id}): título ya existe en {existing_title[title_key]}"
            )

        incoming_tokens = _tokens(_record_text(normalized))
        for existing_id, existing_tokens in existing_vectors:
            similarity = _jaccard(incoming_tokens, existing_tokens)
            if similarity >= NEAR_DUPLICATE_JACCARD:
                raise ValueError(
                    f"registro {index} ({item.id}): posible duplicado de {existing_id} "
                    f"(jaccard={similarity:.2f})"
                )

        validated.append(item)

    return validated, already_present


def process_event(
    event_path: Path,
    memory_path: Path,
    *,
    apply: bool = False,
    now: datetime | None = None,
) -> tuple[str, list[str]]:
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    issue = payload.get("issue") or {}
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "").strip()

    match = TITLE_RE.fullmatch(title)
    if not match:
        raise ValueError("título de staging inválido")
    if not body:
        raise ValueError("issue de staging sin cuerpo")

    local_now = now or datetime.now(TZ)
    issue_date = match.group("date")
    issue_time = match.group("time")
    if issue_date != local_now.date().isoformat():
        raise ValueError(
            f"el staging corresponde a {issue_date}, no a la fecha local actual "
            f"{local_now.date().isoformat()}"
        )

    expected_header = (
        f"# Narrative Memory Staging — {issue_date} {issue_time} America/Mexico_City"
    )
    incoming = _parse_body(body, expected_header)
    existing = _read_existing(memory_path)
    new_items, already_present = _validate_records(incoming, existing, issue_date)

    if not new_items:
        _write_output("status", "already_exists")
        _write_output("added_count", "0")
        _write_output("ids", ",".join(already_present))
        return "already_exists", already_present

    ids = [item.id for item in new_items]
    if apply:
        original = memory_path.read_text(encoding="utf-8")
        if original and not original.endswith("\n"):
            original += "\n"
        additions = "".join(
            json.dumps(item.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")) + "\n"
            for item in new_items
        )
        memory_path.write_text(original + additions, encoding="utf-8")
        status = "applied"
    else:
        status = "validated"

    _write_output("status", status)
    _write_output("added_count", str(len(new_items)))
    _write_output("ids", ",".join(ids))
    return status, ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    parser.add_argument(
        "--memory",
        type=Path,
        default=Path("editorial/narrative_memory.jsonl"),
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not str(args.event):
        print("ERROR: GITHUB_EVENT_PATH/--event requerido", file=sys.stderr)
        return 2

    try:
        status, ids = process_event(args.event, args.memory, apply=args.apply)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"{status}: {','.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
