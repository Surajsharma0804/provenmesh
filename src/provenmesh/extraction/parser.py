"""LLM response parser — safe JSON parsing with validation."""

from __future__ import annotations

import json
from typing import Any

from provenmesh.observability.logging import get_logger

logger = get_logger(__name__)


def parse_llm_response(raw_response: str) -> dict[str, Any]:
    """Safely parse LLM JSON response.

    Handles common LLM output issues:
    - Markdown code blocks (```json ... ```)
    - Extra whitespace
    - Truncated responses
    """
    if not raw_response:
        return {}

    text = raw_response.strip()

    # Remove markdown code block wrapper
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("llm_response_parse_failed", error=str(e), response_preview=text[:200])

        # Try to extract JSON from the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return {}


def extract_evidenced_fields(
    parsed: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Normalize LLM output into evidence-first format.

    Ensures every field has the {value, evidence, confidence} structure
    even if the LLM returned a simpler format.
    """
    result: dict[str, dict[str, Any]] = {}

    for key, value in parsed.items():
        if key == "relationships":
            continue  # Handle separately

        if isinstance(value, dict) and "value" in value:
            # Already in evidence-first format
            result[key] = {
                "value": value.get("value"),
                "evidence": value.get("evidence", ""),
                "confidence": float(value.get("confidence", 0.0)),
            }
        elif isinstance(value, list):
            result[key] = [
                {
                    "value": item.get("value") if isinstance(item, dict) else item,
                    "evidence": item.get("evidence", "") if isinstance(item, dict) else "",
                    "confidence": (
                        float(item.get("confidence", 0.0))
                        if isinstance(item, dict)
                        else 0.0
                    ),
                }
                for item in value
            ]
        else:
            # Wrap simple values
            result[key] = {
                "value": value,
                "evidence": "",
                "confidence": 0.0,
            }

    return result


def extract_relationships(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract relationship candidates from LLM response."""
    relationships = parsed.get("relationships", [])
    if not isinstance(relationships, list):
        return []

    valid: list[dict[str, Any]] = []
    for rel in relationships:
        if isinstance(rel, dict) and "source" in rel and "target" in rel and "type" in rel:
            valid.append({
                "source": rel["source"],
                "target": rel["target"],
                "type": rel["type"],
                "evidence": rel.get("evidence", ""),
                "confidence": float(rel.get("confidence", 0.0)),
            })

    return valid
