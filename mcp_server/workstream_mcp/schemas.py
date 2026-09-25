from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

EMPTY_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}
PROFILE_UPDATE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "display_name": {"type": ["string", "null"], "maxLength": 200},
        "contact_email": {"type": ["string", "null"], "maxLength": 320},
    },
    "minProperties": 1,
    "additionalProperties": False,
}
AUTHORIZATION_CONTEXT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "pattern": r"^[^\u0000]*$",
        }
    },
    "required": ["project_id"],
    "additionalProperties": False,
}


class ContractError(RuntimeError):
    """The reviewed packaged contract is absent or invalid."""


_OUTPUT_FORMAT_CHECKER = FormatChecker()


def _resolve_schema_refs(value: Any, schemas: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_resolve_schema_refs(item, schemas) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    prefix = "#/components/schemas/"
    if isinstance(reference, str) and reference.startswith(prefix):
        target = schemas.get(reference.removeprefix(prefix))
        if not isinstance(target, dict):
            raise ContractError("contract contains an unresolved schema reference")
        return _resolve_schema_refs(target, schemas)
    return {key: _resolve_schema_refs(item, schemas) for key, item in value.items()}


def _selected_schema(document: dict[str, Any]) -> dict[str, Any]:
    for key in ("output_schema", "outputSchema", "schema"):
        candidate = document.get(key)
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
                    return cast(dict[str, Any], _resolve_schema_refs(candidate, schemas))
    raise ContractError("contract does not contain an output schema")


@lru_cache(maxsize=3)
def _contract_output_schema(name: str) -> dict[str, Any]:
    filename = f"{name}.json"
    resource = files("workstream_mcp").joinpath(f"contracts/{filename}")
    try:
        document = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError:
        source_contract = Path(__file__).resolve().parents[1] / "contracts" / filename
        try:
            document = json.loads(source_contract.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ContractError(f"packaged {name} contract is missing or invalid") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"packaged {name} contract is missing or invalid") from exc
    if not isinstance(document, dict):
        raise ContractError(f"{name} contract must be a JSON object")
    schema = _selected_schema(document)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ContractError(f"{name} output schema is invalid") from exc
    return schema


def profile_output_schema() -> dict[str, Any]:
    return _contract_output_schema("profile_get")


def profile_update_output_schema() -> dict[str, Any]:
    return _contract_output_schema("profile_update")


def authorization_context_output_schema() -> dict[str, Any]:
    return _contract_output_schema("authorization_context_get")


@lru_cache(maxsize=3)
def _contract_output_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        _contract_output_schema(name),
        format_checker=_OUTPUT_FORMAT_CHECKER,
    )


def profile_output_validator() -> Draft202012Validator:
    return _contract_output_validator("profile_get")


def profile_update_output_validator() -> Draft202012Validator:
    return _contract_output_validator("profile_update")


def authorization_context_output_validator() -> Draft202012Validator:
    return _contract_output_validator("authorization_context_get")
