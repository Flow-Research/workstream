"""Bound an untrusted private candidate without treating it as accepted policy."""

from __future__ import annotations

from copy import deepcopy
import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import ValidationError

from app.interfaces.project_agents import (
    GENERATED_REQUIREMENT_DISPOSITIONS,
    CapabilityParameter,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    invalid_compilation_failure_code,
    require_complete_generated_specifications,
)
from app.modules.checkers.api.external import ExternalCheckerContractError


SELECTED_CHECK_CORRECTION_GUIDANCE = (
    " Every binding requires configuration_source and parameters. Use registry with empty "
    "parameters only for a uniquely fixed, closed constant configuration of the exact selected "
    "entry/version; the adapter supplies its immutable parameters. Use explicit with your "
    "complete typed parameters, including any fixed fields, for variable, ambiguous, default "
    "or reference schemas. Do not supply the literals of wholly fixed registry-mode configurations. "
    "Registered deadlines determine supported-stage execution "
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
    generated = deepcopy(schema)
    for name in ("PreSubmissionBindingProposal", "PostSubmissionBindingProposal"):
        binding = generated["$defs"][name]
        binding["properties"]["configuration_source"] = {
            "type": "string", "enum": ["registry", "explicit"],
            "description": (
                "registry requires empty parameters and one uniquely fixed registered "
                "configuration; explicit retains typed variable configuration choices."
            ),
        }
        for field in ("configuration_source", "parameters"):
            if field not in binding.setdefault("required", []):
                binding["required"].append(field)
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


def _compact_bytes(value) -> bytes:
    """Measure the complete private/canonical proposal with exact UTF-8 JSON bytes."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _fixed_registry_parameters(entry) -> list[dict] | None:
    """Certify one closed literal object, never infer branches, defaults or references."""
    document = entry.configuration_schema.document
    pending = [(document, False)]
    while pending:
        node, names_only = pending.pop()
        if isinstance(node, dict):
            if not names_only and (any(key in node for key in (
                "$ref", "$dynamicRef", "$recursiveRef", "default", "anyOf", "allOf",
                "if", "then", "else", "not",
            )) or ("oneOf" in node and node is not document)):
                return None
            pending.extend((value, not names_only and key in {"properties", "patternProperties", "$defs", "definitions"})
                           for key, value in node.items())
        elif isinstance(node, list):
            pending.extend((value, False) for value in node)
    branch = document
    if "oneOf" in document:
        if not isinstance(document["oneOf"], list) or len(document["oneOf"]) != 1:
            return None
        branch = document["oneOf"][0]
    properties = branch.get("properties") if isinstance(branch, dict) else None
    required = branch.get("required") if isinstance(branch, dict) else None
    if (
        not isinstance(properties, dict) or len(properties) > 50
        or branch.get("type") != "object" or branch.get("additionalProperties") is not False
        or not isinstance(required, list) or len(required) != len(properties)
        or any(type(name) is not str for name in required)
        or set(required) != set(properties)
        or any(not isinstance(value, dict) or "const" not in value for value in properties.values())
    ):
        return None
    try:
        parameters = [
            CapabilityParameter.model_validate_json(_compact_bytes({
                "name": name, "value": properties[name]["const"],
            })).model_dump(mode="json")
            for name in sorted(properties)
        ]
        entry.configuration_schema.validate_instance({p["name"]: p["value"] for p in parameters})
    except (TypeError, ValueError):
        return None
    return parameters


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

    def canonical_candidate(self, context, candidate: dict) -> dict | None:
        """Resolve only the required private mode on a detached, byte-bounded proposal."""
        self.unsafe_text = False
        canonical = deepcopy(candidate)
        modes = []
        for phase in ("pre_submit", "post_submit"):
            field = phase + "_bindings"
            for index, binding in enumerate(canonical[field]):
                mode = binding.pop("configuration_source", None)
                modes.append((phase, field, index, mode))
        # A mode error cannot license echoing unsafe text from another field.
        # Required private metadata is removed before the existing text owner runs.
        early_issues = self.canonical_issues(canonical)
        if self.unsafe_text:
            self.issues = early_issues
            return None
        size = len(_compact_bytes(canonical))
        definitions = {
            (item.phase, item.capability_id, item.capability_version): item
            for item in context.checker_capabilities.definitions
        }
        for phase, field, index, mode in modes:
            binding = canonical[field][index]
            if mode not in ("registry", "explicit"):
                self.issues = [{"path": [field, index, "configuration_source"],
                                "code": "configuration_source_required"}]
                return None
            definition = definitions.get((phase, binding["capability_id"], binding["capability_version"]))
            entry = definition.registry_entry if definition is not None else None
            if (
                definition is None or not definition.selectable or entry is None
                or binding["stage"] != phase or entry.phase != phase
                or entry.capability_id != binding["capability_id"]
                or entry.capability_version != binding["capability_version"]
            ):
                self.issues = [{"path": [field, index], "code": "binding_reference"}]
                return None
            fixed = _fixed_registry_parameters(entry)
            if mode == "registry":
                if binding["parameters"]:
                    self.issues = [{"path": [field, index, "parameters"],
                                    "code": "registry_parameters_forbidden"}]
                    return None
                if fixed is None:
                    self.issues = [{"path": [field, index, "configuration_source"],
                                    "code": "registry_configuration_unavailable"}]
                    return None
                size += len(_compact_bytes(fixed)) - len(b"[]")
                if size > self._maximum_bytes:
                    self.issues = [{"path": [], "code": "expanded_output_too_large"}]
                    return None
                binding["parameters"] = fixed
            elif fixed is not None:
                self.issues = [{"path": [field, index, "configuration_source"],
                                "code": "registry_configuration_required"}]
                return None
        if len(_compact_bytes(canonical)) > self._maximum_bytes:
            self.issues = [{"path": [], "code": "expanded_output_too_large"}]
            return None
        self.issues = self.canonical_issues(canonical)
        return None if self.issues else canonical

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
