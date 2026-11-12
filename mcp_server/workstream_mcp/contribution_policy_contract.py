"""Policy-view relationships that JSON Schema cannot express across parent fields."""

from __future__ import annotations

import re
from collections.abc import Iterator
from copy import deepcopy
from typing import Any
from uuid import UUID

from jsonschema import (  # type: ignore[import-untyped]
    Draft202012Validator,
    ValidationError,
    validators,
)

_QUANTITY = re.compile(r"(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?")
_UNIT = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,31}")
_CURRENCY = re.compile(r"[A-Z]{3}")
_KEYWORD = "x-workstream-policy-view"


def _closed_policy_view(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    marker, rules = value.get("reward_model_version"), value.get("rules")
    if type(value.get("version_number")) is not int or value["version_number"] < 1:
        return False
    if not isinstance(value.get("name"), str) or not value["name"].strip():
        return False
    header = tuple(value.get(key) for key in ("instrument_type", "unit_code", "adapter_binding_id"))
    if type(marker) is not int or marker not in (1, 2) or not isinstance(rules, list):
        return False
    if not rules:
        return value.get("version_status") == "draft" and all(item is None for item in header)
    if len(rules) != 2 or marker == 1 and any(item is not None for item in header):
        return False
    kinds: set[str] = set()
    definition_ids: set[UUID] = set()
    rule_ids: set[UUID] = set()
    paid = False
    try:
        for rule in rules:
            if not isinstance(rule, dict):
                return False
            kind, mode = rule.get("contribution_type"), rule.get("compensation_mode")
            definitions = rule.get("definitions")
            if kind not in ("accepted_submission", "completed_review") or kind in kinds:
                return False
            kinds.add(kind)
            rule_id = UUID(rule.get("rule_id"))
            if rule_id in rule_ids or not isinstance(definitions, list):
                return False
            rule_ids.add(rule_id)
            if mode == "unpaid":
                if definitions:
                    return False
                continue
            if mode != "compensated":
                return False
            paid = True
            expected = 3 if kind == "accepted_submission" else 1
            if marker == 1:
                if not 1 <= len(definitions) <= 2:
                    return False
            elif len(definitions) != expected:
                return False
            sizes, instruments = set(), set()
            for definition in definitions:
                if not isinstance(definition, dict):
                    return False
                if (
                    type(definition.get("reward_model_version")) is not int
                    or definition["reward_model_version"] != marker
                ):
                    return False
                definition_id = UUID(definition.get("definition_id"))
                if definition_id in definition_ids:
                    return False
                definition_ids.add(definition_id)
                instrument, unit, quantity = (
                    definition.get(key) for key in ("instrument_type", "unit_code", "quantity")
                )
                binding = UUID(definition.get("adapter_binding_id"))
                if (
                    not isinstance(unit, str)
                    or not isinstance(quantity, str)
                    or _QUANTITY.fullmatch(quantity) is None
                    or not any(char in "123456789" for char in quantity)
                ):
                    return False
                if instrument == "money":
                    if _CURRENCY.fullmatch(unit) is None:
                        return False
                elif instrument == "project_points":
                    if _UNIT.fullmatch(unit) is None or "." in quantity:
                        return False
                else:
                    return False
                size = definition.get("task_size")
                if marker == 1:
                    if size is not None or instrument in instruments:
                        return False
                else:
                    if (instrument, unit) != header[:2] or binding != UUID(header[2]):
                        return False
                    if kind == "accepted_submission":
                        if size not in ("small", "medium", "large") or size in sizes:
                            return False
                        sizes.add(size)
                    elif size is not None:
                        return False
                instruments.add(instrument)
    except (TypeError, ValueError, AttributeError):
        return False
    return marker == 1 or (
        all(item is not None for item in header) if paid else all(item is None for item in header)
    )


def _policy_view_errors(
    _validator: Any, enabled: bool, instance: Any, _schema: Any
) -> Iterator[ValidationError]:
    if enabled and not _closed_policy_view(instance):
        yield ValidationError(
            "policy view must contain an empty draft or one complete exact reward graph"
        )


def _exact_integer(_checker: Any, instance: Any) -> bool:
    return type(instance) is int


_PolicyViewValidator = validators.extend(
    Draft202012Validator,
    {_KEYWORD: _policy_view_errors},
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine("integer", _exact_integer),
)


def policy_view_output_validator(
    schema: dict[str, Any], *, collection: bool, format_checker: Any
) -> Draft202012Validator:
    """Keep read and list validation identical while preserving the frozen public schema."""
    checked = deepcopy(schema)
    view = checked["properties"]["items"]["items"] if collection else checked
    view[_KEYWORD] = True
    return _PolicyViewValidator(checked, format_checker=format_checker)
