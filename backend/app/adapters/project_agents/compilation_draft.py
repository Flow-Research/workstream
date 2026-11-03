"""Bound an untrusted private candidate without treating it as accepted policy."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import ValidationError

from app.interfaces.project_agents import (
    GENERATED_REQUIREMENT_DISPOSITIONS,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    invalid_compilation_failure_code,
    require_complete_generated_specifications,
)
from app.modules.checkers.api.external import ExternalCheckerContractError


SELECTED_CHECK_CORRECTION_GUIDANCE = (
    " When selected_configuration_contracts are supplied, copy the complete configuration "
    "from each exact selected registry schema. Keep profile IDs, versions and digests "
    "together; do not mix tuples. Registered deadlines determine supported-stage execution "
    "cost; lowering declared durations cannot reduce that cost. Preserve every source "
    "obligation and all limits. Group checks only when methods, inputs and stages match; "
    "never drop checks to fit the budget."
)


def _unique_object(pairs):
    """Reject duplicate JSON members instead of silently selecting one value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(_value):
    """Reject nonstandard JSON numeric constants without copying their text."""
    raise ValueError("nonstandard JSON constant")


def generated_compilation_schema(schema: dict) -> dict:
    """Restrict new model output while retaining immutable historical read schemas."""
    from copy import deepcopy

    generated = deepcopy(schema)
    generated["$defs"]["RequirementDisposition"]["enum"] = sorted(
        item.value for item in GENERATED_REQUIREMENT_DISPOSITIONS
    )
    generated["$defs"]["AtomicGuideRequirement"]["properties"]["disposition"]["enum"] = sorted(
        item.value for item in GENERATED_REQUIREMENT_DISPOSITIONS
    )
    generated["$defs"]["AtomicGuideRequirement"]["properties"]["disposition"]["description"] = (
        "Classify only submission checks: supported or missing PRE/POST capabilities, "
        "exact default PRE coverage, or guide defects preventing check specification."
    )
    del generated["properties"]["setup_notes"]
    if "setup_notes" in generated.get("required", []):
        generated["required"].remove("setup_notes")
    return generated


def _configuration_const_paths(error: SchemaValidationError):
    """Locate constants only when the owner reports an unambiguous schema branch."""
    if error.validator == "const":
        yield tuple(error.absolute_path)
    elif error.validator == "oneOf" and len(error.schema["oneOf"]) == 1:
        for child in error.context:
            yield from _configuration_const_paths(child)


_BUDGET_ISSUES = {
    message: {"path": [stage + "_bindings"], "code": code}
    for stage in ("pre_submit", "post_submit")
    for message, code in (
        (
            f"supported {stage.replace('_', '-')} checks exceed the aggregate execution budget",
            "aggregate_execution_budget",
        ),
        (
            f"proposed {stage.replace('_', '-')} checks require an execution capacity gap",
            "execution_capacity_required",
        ),
        (
            f"proposed {stage.replace('_', '-')} checks do not require an execution capacity gap",
            "execution_capacity_unneeded",
        ),
    )
}


def _selected_binding_issues(context, result) -> list[dict]:
    """Report independent selected-check violations with only trusted field metadata."""
    result = ProjectGuideCompilationResult.model_validate(result)
    definitions = {
        (item.phase, item.capability_id, item.capability_version): item
        for item in context.checker_capabilities.definitions
    }
    requirements = {}
    for index, requirement in enumerate(result.requirements):
        key = requirement.requirement_id
        requirements[key] = None if key in requirements else (index, requirement)
    issues = []
    for phase in ("pre_submit", "post_submit"):
        field = phase + "_bindings"
        for binding_index, binding in enumerate(getattr(result, field)):
            definition = definitions.get((phase, binding.capability_id, binding.capability_version))
            if definition is None or definition.registry_entry is None:
                continue
            configuration = {
                item.name: item.model_dump(mode="json")["value"] for item in binding.parameters
            }
            try:
                definition.registry_entry.configuration_schema.validate_instance(configuration)
            except ExternalCheckerContractError as error:
                paths = (
                    _configuration_const_paths(error.__cause__)
                    if isinstance(error.__cause__, SchemaValidationError) else ()
                )
                for path in paths:
                    if not path:
                        continue
                    for parameter_index, parameter in enumerate(binding.parameters):
                        if parameter.name == path[0]:
                            issue = {
                                "path": [
                                    field,
                                    binding_index,
                                    "parameters",
                                    parameter_index,
                                    "value",
                                ],
                                "code": "schema_const",
                            }
                            if issue not in issues:
                                issues.append(issue)
                            if len(issues) == 20:
                                return issues
            selected = requirements.get(binding.requirement_id)
            if (
                selected is None
                or binding.stage.value != phase
                or not definition.selectable
            ):
                continue
            requirement_index, requirement = selected
            specification = requirement.check_specification
            if (
                requirement.disposition.value != "supported_" + phase
                or specification is None
            ):
                continue
            deadline_ms = definition.registry_entry.resources.deadline_ms
            if specification.maximum_duration_seconds * 1000 > deadline_ms:
                issues.append({
                    "path": [
                        "requirements", requirement_index, "check_specification",
                        "maximum_duration_seconds",
                    ],
                    "code": "checker_deadline",
                    "checker_deadline_ms": deadline_ms,
                })
                if len(issues) == 20:
                    return issues
    try:
        require_complete_generated_specifications(context, result)
    except ValueError as error:
        issue = _BUDGET_ISSUES.get(str(error))
        if issue is not None:
            issues.append({"path": list(issue["path"]), "code": issue["code"]})
    return issues


def selected_configuration_correction_context(context, result, issues) -> list[dict]:
    """Repeat only affected immutable registry contracts in the private model prompt."""
    if result is None or not any(issue.get("code") == "schema_const" for issue in issues):
        return []
    try:
        result = ProjectGuideCompilationResult.model_validate(result)
    except ValidationError:
        return []
    definitions = {
        (item.phase, item.capability_id, item.capability_version): item
        for item in context.checker_capabilities.definitions
    }
    selected = {}
    for issue in issues[:20]:
        path = issue.get("path", [])
        if (
            issue.get("code") != "schema_const"
            or len(path) != 5
            or path[0] not in ("pre_submit_bindings", "post_submit_bindings")
            or type(path[1]) is not int
            or path[1] < 0
            or path[2] != "parameters"
            or type(path[3]) is not int
            or path[3] < 0
            or path[4] != "value"
        ):
            continue
        phase = path[0].removesuffix("_bindings")
        bindings = getattr(result, path[0])
        if path[1] >= len(bindings):
            continue
        binding = bindings[path[1]]
        definition = definitions.get((phase, binding.capability_id, binding.capability_version))
        if (
            binding.stage.value != phase
            or path[3] >= len(binding.parameters)
            or definition is None
            or not definition.selectable
            or definition.registry_entry is None
        ):
            continue
        entry = definition.registry_entry
        key = str(entry.registry_entry_id)
        if key not in selected:
            selected[key] = {
                "binding_paths": [],
                "capability_id": definition.capability_id,
                "capability_version": definition.capability_version,
                "registry_entry_id": key,
                "registry_entry_digest": entry.entry_digest,
                "configuration_schema": entry.configuration_schema.model_dump(mode="json"),
            }
        binding_path = path[:2]
        if binding_path not in selected[key]["binding_paths"]:
            selected[key]["binding_paths"].append(binding_path)
    return list(selected.values())


def contextual_output_issues(
    error: Exception,
    *,
    context: ProjectGuideCompilationContext,
    result: ProjectGuideCompilationResult | dict,
) -> list[dict]:
    """Map owner failures to bounded diagnostics without rejected values or exception text."""
    configuration_error = isinstance(error, ExternalCheckerContractError) and isinstance(
        error.__cause__, SchemaValidationError
    )
    deadline_error = isinstance(error, ValueError) and str(error) == (
        "check specification exceeds the checker deadline"
    )
    budget_error = isinstance(error, ValueError) and str(error) in _BUDGET_ISSUES
    if configuration_error or deadline_error or budget_error:
        issues = _selected_binding_issues(context, result)
        if issues:
            return issues
    codes = {
        "generated requirement is outside PRE and POST checker scope": "checker_scope",
        "generated setup notes are outside checker specification scope": "unknown_field",
        "model evaluation requires post-submit background work": "model_requires_post",
        "pre-submit check specification is not bounded": "pre_duration",
        "post-submit check specification is not background work": "post_background",
        "supported check depends on unavailable runtime support": "unavailable_dependency",
        "supported compilation requirements must have one binding": "binding_count",
        "compilation requirements must be unique": "requirement_ids_unique",
        "blocked compilation requires blocking evidence": "blocked_evidence",
        "ready compilation cannot contain blocking evidence": "ready_blocking_evidence",
        "draft-ready compilation cannot contain warnings": "ready_warnings",
        "warning-ready compilation requires a warning": "warning_evidence",
        "blocked guide cannot publish policy proposals": "blocked_artifact_policy",
        "draft-ready compilation requires artifact policy": "artifact_policy_required",
        "capability gaps must have exactly one suggestion": "suggestion_count",
        "compilation capability suggestion is invalid": "suggestion_reference",
        "compilation capability binding is invalid": "binding_reference",
        "compilation capability version is stale": "binding_version",
        "compilation evidence does not resolve to source lineage": "source_identity",
        "ready compilation does not account for every assigned document": "source_coverage",
        "compilation has no opened document evidence": "source_not_opened",
        "compilation cites unopened source material": "source_not_opened",
        "compilation did not open every assigned original": "source_coverage",
        "platform coverage does not resolve to canonical truth": "platform_coverage",
        "non-platform requirement cannot claim platform coverage": "platform_coverage",
    }
    return [{"path": [], "code": codes.get(str(error), "context_constraint")}]


class CompilationDraftParser:
    """Use the canonical SDK schema for structure, leaving correction to review."""

    def __init__(self, schema: dict, maximum_bytes: int) -> None:
        """Cache a trusted local-only schema and its bounded diagnostic field names."""
        pending = [schema]
        self._fields = set()
        while pending:
            node = pending.pop()
            if isinstance(node, dict):
                if "$id" in node or any(
                    key in node
                    and (not isinstance(node[key], str) or not node[key].startswith("#/"))
                    for key in ("$ref", "$dynamicRef", "$recursiveRef")
                ):
                    raise ValueError("guide draft schema must use only local references")
                self._fields.update(node.get("properties", {}))
                pending.extend(node.values())
            elif isinstance(node, list):
                pending.extend(node)
        self._validator = Draft202012Validator(schema)
        self._maximum_bytes = maximum_bytes
        self.unsafe_text = False

    def _path(self, parts) -> list:
        """Return only trusted schema field names and bounded array ordinals."""
        return [
            part if type(part) is int or part in self._fields else "<field>"
            for part in list(parts)[:16]
        ]

    def parse(self, raw: str) -> dict | None:
        """Return only bounded structural data; failed parsing exposes no error object."""
        self.issues = [{"path": [], "code": "invalid_json"}]
        self.unsafe_text = False
        try:
            if len(raw.encode("utf-8")) > self._maximum_bytes:
                return None
            candidate = json.loads(
                raw,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            if not isinstance(candidate, dict):
                return None
            errors = []
            for error in self._validator.iter_errors(candidate):
                errors.append(
                    {
                        "path": self._path(error.absolute_path),
                        "code": "schema_" + str(error.validator),
                    }
                )
                if len(errors) == 20:
                    break
            if errors:
                self.issues = errors
                return None
            # Escaped lone surrogates and non-finite numeric overflow must not
            # become serialization failures after the provider boundary.
            json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, RecursionError, UnicodeError, SchemaValidationError):
            return None
        self.issues = []
        return candidate

    def canonical_issues(self, candidate: dict) -> list[dict]:
        """Identify failing fields without forwarding rejected values or error messages."""
        self.unsafe_text = False
        codes = {
            "model-produced text is unsafe": "unsafe_text",
            "check dependency availability is invalid": "dependency_availability",
            "isolated evaluation requires an execution dependency": "isolated_dependency",
            "model evaluation requires a model service dependency": "model_dependency",
            "check context input requires a runtime dependency": "context_dependency",
            "check material dependency requires a declared input": "dependency_input",
            "check dependency failure is not specified": "dependency_failure",
        }
        try:
            ProjectGuideCompilationResult.model_validate(candidate)
        except ValidationError as error:
            self.unsafe_text = invalid_compilation_failure_code(error) == "unsafe_text"
            return [
                {
                    "path": [
                        part if isinstance(part, int) or part in self._fields else "<field>"
                        for part in item["loc"][:16]
                    ],
                    "code": codes.get(
                        str((item.get("ctx") or {}).get("error")),
                        "canonical_constraint",
                    ),
                }
                for item in error.errors(
                    include_input=False, include_context=True, include_url=False
                )[:20]
            ]
        return []
