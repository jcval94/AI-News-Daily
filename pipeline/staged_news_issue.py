from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.news import classify_url, parse_news_file
from pipeline.source_naming import files_for_date, source_date, source_sort_key

TZ = ZoneInfo("America/Mexico_City")
ALLOWED = {"modelos", "agentes", "investigación", "empresas", "regulación", "hardware", "producto"}
FIELDS = ("Título", "Fecha", "Fuente", "Enlace", "Resumen breve", "Por qué importa", "Categoría")
STAMP = r"(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2})"
TITLE_RE = re.compile(rf"^AI_NEWS_STAGING — {STAMP} America/Mexico_City$")
HEADER_RE = re.compile(rf"^# AI News Daily — {STAMP} America/Mexico_City$")


def _items(path: Path):
    try:
        return parse_news_file(path)
    except (OSError, UnicodeError, ValueError):
        return []


def valid_for_day(news_dir: Path, day: date) -> Path | None:
    for path in files_for_date(news_dir, day):
        if _items(path):
            return path
    return None


def recent_valid(news_dir: Path, today: date, limit: int = 3) -> list[Path]:
    by_day: dict[date, list[Path]] = {}
    for path in news_dir.glob("*.txt"):
        day = source_date(path)
        if day is not None and day < today:
            by_day.setdefault(day, []).append(path)
    out: list[Path] = []
    for day in sorted(by_day, reverse=True):
        for path in sorted(by_day[day], key=source_sort_key, reverse=True):
            if _items(path):
                out.append(path)
                break
        if len(out) == limit:
            break
    return out


def _title_key(text: str) -> str:
    return " ".join(re.sub(r"[^\wáéíóúüñ]+", " ", text.casefold()).split())


def validate_digest(text: str, expected_header: str, recent: list[Path] | None = None) -> list[str]:
    recent = recent or []
    value = text.strip()
    errors: list[str] = []
    lines = value.splitlines()
    if not lines or lines[0] != expected_header:
        return ["encabezado incorrecto"]
    match = HEADER_RE.fullmatch(lines[0])
    if not match:
        return ["encabezado no canónico"]

    digest_day = date.fromisoformat(match.group("date"))
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / f"{digest_day}-00-00-00.txt"
        probe.write_text(value + "\n", encoding="utf-8")
        try:
            items = parse_news_file(probe)
        except ValueError as exc:
            return [f"parser: {exc}"]

    if not 5 <= len(items) <= 10:
        errors.append(f"cantidad inválida: {len(items)}")

    prior_titles = {_title_key(item.title) for path in recent for item in _items(path)}
    prior_urls = {item.url.strip() for path in recent for item in _items(path) if item.url.strip()}
    titles: set[str] = set()
    urls: set[str] = set()

    for item in items:
        tag = f"item {item.item_index}"
        for field in FIELDS:
            if len(re.findall(rf"(?mi)^{re.escape(field)}\s*:", item.raw_content)) != 1:
                errors.append(f"{tag}: campo {field} inválido")

        title = _title_key(item.title)
        if title in titles:
            errors.append(f"{tag}: título duplicado")
        titles.add(title)

        url = item.url.strip()
        if url in urls:
            errors.append(f"{tag}: URL duplicada")
        urls.add(url)

        if classify_url(url) != "article":
            errors.append(f"{tag}: enlace no concreto")
        if item.category not in ALLOWED:
            errors.append(f"{tag}: categoría inválida {item.category!r}")

        try:
            item_day = date.fromisoformat(item.date)
            if item_day > digest_day or item_day < digest_day - timedelta(days=7):
                errors.append(f"{tag}: fecha fuera de ventana")
        except ValueError:
            errors.append(f"{tag}: fecha inválida")

        if len(item.summary.strip()) < 120:
            errors.append(f"{tag}: resumen demasiado corto")

        why = item.why_it_matters.strip()
        if (
            len(why) < 350
            or "¿" not in why
            or "Hipótesis editorial:" not in why
            or "Qué habría que investigar:" not in why
        ):
            errors.append(f"{tag}: análisis editorial insuficiente")

        if (title in prior_titles or url in prior_urls) and "actualización material" not in item.summary.casefold():
            errors.append(f"{tag}: repetición reciente sin actualización material")

    return errors


def _write_output(name: str, value: str) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def process_event(event_path: Path, news_dir: Path) -> tuple[str, Path | None]:
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    issue = payload.get("issue") or {}
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "").strip()

    title_match = TITLE_RE.fullmatch(title)
    if not title_match:
        raise ValueError("título de staging inválido")
    if not body:
        raise ValueError("issue de staging sin cuerpo")

    issue_day = date.fromisoformat(title_match.group("date"))
    issue_time = title_match.group("time")
    now = datetime.now(TZ)
    local_today = now.date()
    oldest_allowed = local_today - timedelta(days=1)
    if issue_day < oldest_allowed or issue_day > local_today:
        raise ValueError(
            f"el staging corresponde a {issue_day}; sólo se admite la fecha local actual "
            f"{local_today} o el día anterior {oldest_allowed} para recuperación acotada"
        )

    expected_header = f"# AI News Daily — {issue_day.isoformat()} {issue_time} America/Mexico_City"
    first_line = body.splitlines()[0].strip()
    if first_line != expected_header:
        raise ValueError("timestamp del título y encabezado no coincide")

    news_dir.mkdir(parents=True, exist_ok=True)
    existing = valid_for_day(news_dir, issue_day)
    if existing:
        _write_output("status", "already_exists")
        _write_output("path", str(existing))
        _write_output("date", issue_day.isoformat())
        return "already_exists", existing

    recent = recent_valid(news_dir, issue_day, 3)
    errors = validate_digest(body, expected_header, recent)
    if errors:
        raise ValueError("digest rechazado: " + " | ".join(errors))

    output = news_dir / f"{issue_day.isoformat()}-{issue_time.replace(':', '-')}.txt"
    if output.exists():
        raise ValueError(f"la ruta de salida ya existe: {output}")

    output.write_text(body + "\n", encoding="utf-8")
    _write_output("status", "created")
    _write_output("path", str(output))
    _write_output("date", issue_day.isoformat())
    return "created", output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    parser.add_argument("--news-dir", type=Path, default=Path("news"))
    args = parser.parse_args(argv)

    if not str(args.event):
        print("ERROR: GITHUB_EVENT_PATH/--event requerido", file=sys.stderr)
        return 2

    try:
        status, path = process_event(args.event, args.news_dir)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"{status}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
