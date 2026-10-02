from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from pipeline.gdrive_envelope import decode_payload, parse_envelope

MESSAGE_PREFIX = "ai-news-daily.research-weekly."
TARGET_RE = re.compile(r"^research/weekly/(?P<date>\d{4}-\d{2}-\d{2})\.json$")


def _write_output(name: str, value: str) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"${name}=${value}\n")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_schema(root: Path) -> dict[str, Any]:
    return json.loads((root / "weekly_digest.schema.json").read_text(encoding="utf-8"))


def _validate_schema(payload: dict[str, Any], schema: dict[str, Any]) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda err: [str(part) for part in err.absolute_path],
    )
    if errors:
        rendered = []
        for err in errors[:20]:
            location = ".".join(str(part) for part in err.absolute_path) or "<root>"
            rendered.append(f"${location}: ${err.message}")
        raise ValueError("weekly schema inválido: " + " | ".join(rendered))


def _history_state(weekly_dir: Path, exclude: Path) -> dict[str, dict[str, str]]:
    state: dict[str, dict[str, str]] = {}
    for path in sorted(weekly_dir.glob("*.json")):
        if path.resolve() == exclude.resolve():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"histórico inválido ${path}: ${exc}") from exc
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError(f"histórico inválido ${path}: items no es lista")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"histórico inválido ${path}: item no es objeto")
            item_id = str(item.get("id") or "")
            if not item_id:
                raise ValueError(f"histórico inválido ${path}: id vacío")
            basis = item.get("selection_basis")
            updated_at = item.get("updated_at")
            effective = updated_at or item.get("published_at")
            previous = state.get(item_id)
            if previous is None:
                if basis != "new_publication":
                    raise ValueError(
                        f"histórico inválido ${path}: primera aparición de ${item_id} "
                        "no es new_publication"
                    )
            else:
                if basis != "material_update" or not updated_at:
                    raise ValueError(
                        f"histórico inválido ${path}: repetición de ${item_id} "
                        "sin material_update/updated_at"
                    )
                if str(updated_at) <= str(previous["effective_date"]):
                    raise ValueError(
                        f"histórico inválido ${path}: updated_at de ${item_id} no avanza"
                    )
            state[item_id] = {"effective_date": str(effective or ""), "path": str(path)}
    return state


def _validate_history(payload: dict[str, Any], weekly_dir: Path, target: Path) -> None:
    state = _history_state(weekly_dir, target)
    seen: set[str] = set()
    for index, item in enumerate(payload.get("items", []), start=1):
        item_id = str(item["id"])
        if item_id in seen:
            raise ValueError(f"item ${index}: id duplicado en digest: ${item_id}")
        seen.add(item_id)
        previous = state.get(item_id)
        basis = item["selection_basis"]
        updated_at = item.get("updated_at")
        effective = updated_at or item.get("published_at")
        if previous is None:
            if basis != "new_publication":
                raise ValueError(f"item ${item_id}: primera aparición debe ser new_publication")
        else:
            if basis != "material_update":
                raise ValueError(
                    f"item ${item_id}: ya apareció en ${previous['path']}; debe ser material_update"
                )
            if not updated_at:
                raise ValueError(f"item ${item_id}: material_update requiere updated_at")
            if str(updated_at) <= str(previous["effective_date"]):
                raise ValueError(
                    f"item ${item_id}: updated_at=${updated_at} no es posterior a "
                    f"${previous['effective_date']}"
                )
        state[item_id] = {"effective_date": str(effective or ""), "path": str(target)}


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Applied GenAI Weekly — ${payload['digest_date']}",
        "",
        f"Ventana: **${payload['window']['from']} → ${payload['window']['to']}**",
        "",
        "## Cambios de la semana",
        "",
    ]
    for change in payload["weekly_changes"]:
        lines.append(f"- **${change['summary']}** — ${change['why_it_matters']}")
    lines.extend(["", "## Lecturas seleccionadas", ""])

    for item in payload["items"]:
        lines.extend([
            f"### ${item['title']}",
            "",
            f"- **ID:** ${item['id']}",
            f"- **Tipo:** ${item['type']}",
            f"- **Publicado:** ${item['published_at']}",
            f"- **Actualizado:** ${item.get('updated_at') or '—'}",
            f"- **Organización:** ${item.get('organization') or '—'}",
            f"- **Fuente:** ${item['url']}",
            f"- **Temas:** ${', '.join(item['topics'])}",
            f"- **Prioridad:** ${item['priority']}",
            f"- **Recomendación:** ${item['reading_recommendation']}",
            "",
            "**Resumen**",
            "",
            item["summary"],
            "",
            "**Qué cambió**",
            "",
            item["what_changed"],
            "",
            "**Por qué importa**",
            "",
            item["why_it_matters"],
            "",
            "**Evidencia**",
            "",
        ])
        lines.extend(f"- ${value}" for value in item["evidence"])
        lines.extend(["", "**Limitaciones**", ""])
        lines.extend(f"- ${value}" for value in item["limitations"])
        lines.extend(["", "**Aplicaciones prácticas**", ""])
        lines.extend(f"- ${value}" for value in item["practical_applications"])
        lines.append("")

    implications = payload["practical_implications"]
    lines.extend(["## Implicaciones prácticas", ""])
    for label, key in [("Diseño", "design"), ("Evaluación", "evaluation"), ("Despliegue", "deployment")]:
        lines.extend([f"### ${label}", ""])
        values = implications[key]
        if values:
            lines.extend(f"- ${value}" for value in values)
        else:
            lines.append("- Sin implicaciones adicionales registradas.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def process_envelope(
    envelope_path: Path,
    expected_repo: str,
    research_root: Path,
    *,
    apply: bool = False,
) -> tuple[str, Path, Path]:
    env = parse_envelope(
        envelope_path,
        message_prefix=MESSAGE_PREFIX,
        expected_repo=expected_repo,
        expected_content_type="application/json",
    )
    match = TARGET_RE.fullmatch(env["target_path"])
    if not match:
        raise ValueError("target_path debe ser research/weekly/YYYY-MM-DD.json")
    target_date = match.group("date")
    if not env["message_id"].startswith(f"${MESSAGE_PREFIX}${target_date}"):
        raise ValueError("message_id no coincide con target_path")

    payload_text = decode_payload(env)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"payload JSON inválido: ${exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload semanal debe ser un objeto JSON")

    schema = _load_schema(research_root)
    _validate_schema(payload, schema)

    if payload["digest_date"] != target_date:
        raise ValueError("digest_date no coincide con target_path")
    if payload["window"]["to"] != target_date:
        raise ValueError("window.to debe coincidir con digest_date")

    weekly_dir = research_root / "weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    target_json = weekly_dir / f"${target_date}.json"
    target_md = weekly_dir / f"${target_date}.md"
    _validate_history(payload, weekly_dir, target_json)

    normalized_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    normalized_md = render_markdown(payload)
    existing_json = target_json.read_text(encoding="utf-8") if target_json.exists() else None
    existing_md = target_md.read_text(encoding="utf-8") if target_md.exists() else None

    if existing_json is not None and _canonical(json.loads(existing_json)) == _canonical(payload) and existing_md == normalized_md:
        status = "already_exists"
    else:
        status = "updated" if existing_json is not None else "created"
        if apply:
            target_json.write_text(normalized_json, encoding="utf-8")
            target_md.write_text(normalized_md, encoding="utf-8")

    _write_output("status", status)
    _write_output("date", target_date)
    _write_output("json_path", str(target_json))
    _write_output("md_path", str(target_md))
    return status, target_json, target_md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--research-root", type=Path, default=Path("research"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        status, json_path, md_path = process_envelope(
            args.envelope, args.repo, args.research_root, apply=args.apply
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: ${exc}", file=sys.stderr)
        return 1
    print(f"${status}: ${json_path} ${md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
