"""Minimal Responses API adapter for the isolated stress harness."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from .models import RunConfig


HERE = Path(__file__).resolve().parent
CONTRACTS = HERE.parent / "contracts"


class LLMCallError(RuntimeError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    path = CONTRACTS / name
    return json.loads(path.read_text(encoding="utf-8"))


def _output_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for output in response.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    text = "".join(parts).strip()
    if not text:
        raise LLMCallError("Responses API returned no output_text")
    return text


def call_structured(
    *,
    system_prompt: str,
    user_prompt: str,
    schema_file: str,
    schema_name: str,
    config: RunConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise LLMCallError("OPENAI_API_KEY is required for live stress runs")

    schema = load_schema(schema_file)
    body: dict[str, Any] = {
        "model": config.model,
        "store": False,
        "instructions": system_prompt,
        "input": user_prompt,
        "max_output_tokens": config.max_output_tokens,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }
    if config.reasoning_effort != "none":
        body["reasoning"] = {"effort": config.reasoning_effort}

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=config.timeout_seconds,
        )
    except requests.RequestException as exc:
        raise LLMCallError(f"Responses API transport error: {type(exc).__name__}: {exc}") from exc

    if response.status_code >= 400:
        safe = response.text[:1200].replace(key, "***")
        raise LLMCallError(f"Responses API HTTP {response.status_code}: {safe}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMCallError("Responses API returned non-JSON response") from exc

    if payload.get("status") != "completed":
        raise LLMCallError(
            "Responses API did not complete: "
            + json.dumps(
                {
                    "id": payload.get("id"),
                    "status": payload.get("status"),
                    "incomplete_details": payload.get("incomplete_details"),
                },
                ensure_ascii=False,
            )
        )

    raw = _output_text(payload)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMCallError("Structured response was not valid JSON") from exc

    metadata = {
        "response_id": payload.get("id"),
        "model": payload.get("model") or config.model,
        "usage": payload.get("usage"),
        "status": payload.get("status"),
    }
    return parsed, metadata
