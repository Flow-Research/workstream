from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class ContractError(RuntimeError):
    """The reviewed packaged contract is absent or invalid."""


def _selected_schema(document: dict[str, Any]) -> dict[str, Any]:
    for key in ("output_schema", "outputSchema", "schema"):
        candidate = document.get(key)
        if isinstance(candidate, dict):
            return candidate
    components = document.get("components")
    if isinstance(components, dict):
        schemas = components.get("schemas")
        if isinstance(schemas, dict):
            candidate = schemas.get("ActorProfileSelfResponse")
            if isinstance(candidate, dict):
                return candidate
    if document.get("type") == "object":
        return document
    operation = document.get("operation")
    components = document.get("components")
    if isinstance(operation, dict) and isinstance(components, dict):
        schemas = components.get("schemas")
        responses = operation.get("responses")
        if isinstance(schemas, dict) and isinstance(responses, dict):
            success = responses.get("200")
            content = success.get("content") if isinstance(success, dict) else None
            media = content.get("application/json") if isinstance(content, dict) else None
            selected = media.get("schema") if isinstance(media, dict) else None
            reference = selected.get("$ref") if isinstance(selected, dict) else None
            prefix = "#/components/schemas/"
            if isinstance(reference, str) and reference.startswith(prefix):
                candidate = schemas.get(reference.removeprefix(prefix))
                if isinstance(candidate, dict):
                    return candidate
    raise ContractError("profile_get contract does not contain an output schema")


@lru_cache(maxsize=1)
def profile_output_schema() -> dict[str, Any]:
    resource = files("workstream_mcp").joinpath("contracts/profile_get.json")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError:
        source_contract = Path(__file__).resolve().parents[1] / "contracts" / "profile_get.json"
        try:
            document = json.loads(source_contract.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ContractError("packaged profile_get contract is missing or invalid") from exc
    except json.JSONDecodeError as exc:
        raise ContractError("packaged profile_get contract is missing or invalid") from exc
    if not isinstance(document, dict):
        raise ContractError("profile_get contract must be a JSON object")
    schema = _selected_schema(document)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ContractError("profile_get output schema is invalid") from exc
    return schema


@lru_cache(maxsize=1)
def profile_output_validator() -> Draft202012Validator:
    return Draft202012Validator(profile_output_schema())
