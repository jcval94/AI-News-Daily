"""JSON Schema loading and validation for the isolated stress lab."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


@lru_cache(maxsize=1)
def _resources() -> tuple[dict[str, dict[str, Any]], Registry]:
    schemas: dict[str, dict[str, Any]] = {}
    registry = Registry()
    for path in sorted(CONTRACTS.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schemas[path.name] = schema
        identifier = str(schema.get("$id") or "")
        if identifier:
            registry = registry.with_resource(identifier, Resource.from_contents(schema))
    return schemas, registry


def schema(name: str) -> dict[str, Any]:
    schemas, _ = _resources()
    if name not in schemas:
        raise KeyError(f"Unknown stress contract: {name}")
    return schemas[name]


def validate(name: str, payload: Any) -> None:
    schemas, registry = _resources()
    if name not in schemas:
        raise KeyError(f"Unknown stress contract: {name}")
    Draft202012Validator(schemas[name], registry=registry).validate(payload)


def contract_names() -> list[str]:
    schemas, _ = _resources()
    return sorted(schemas)
