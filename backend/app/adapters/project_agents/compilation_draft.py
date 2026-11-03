"""Bound untrusted private proposals without granting policy authority."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import ValidationError

from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    invalid_compilation_failure_code,
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


def contextual_output_issues(error: Exception, *, context, result) -> list[dict]:
    """Map validation failures to bounded diagnostics without rejected values."""
    if str(error) == "compilation result agent version is invalid":
        return [{"path": ["agent_version"], "code": "agent_version"}]
    codes = {
        "compilation requirements must be unique": "suggestion_ids_unique",
        "blocked compilation requires blocking evidence": "blocked_evidence",
        "ready compilation cannot contain blocking evidence": "ready_blocking_evidence",
        "draft-ready compilation cannot contain warnings": "ready_warnings",
        "warning-ready compilation requires a warning": "warning_evidence",
        "blocked guide cannot publish policy proposals": "blocked_artifact_policy",
        "draft-ready compilation requires artifact policy": "artifact_policy_required",
        "compilation evidence does not resolve to source lineage": "source_identity",
        "ready compilation does not account for every assigned document": "source_coverage",
        "compilation has no opened document evidence": "source_not_opened",
        "compilation cites unopened source material": "source_not_opened",
        "compilation did not open every assigned original": "source_coverage",
    }
    return [{"path": [], "code": codes.get(str(error), "context_constraint")}]


class CompilationDraftParser:
    """Validate bounded JSON against the current specification schema."""

    def __init__(self, schema: dict, maximum_bytes: int) -> None:
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
        self.issues: list[dict] = []

    def _path(self, parts) -> list:
        return [
            part if type(part) is int or part in self._fields else "<field>"
            for part in list(parts)[:16]
        ]

    def parse(self, raw: str) -> dict | None:
        """Return only bounded structural data; never expose a rejected value."""
        self.issues = [{"path": [], "code": "invalid_json"}]
        self.unsafe_text = False
        try:
            if len(raw.encode("utf-8")) > self._maximum_bytes:
                return None
            candidate = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            if not isinstance(candidate, dict):
                return None
            errors = []
            for error in self._validator.iter_errors(candidate):
                errors.append({"path": self._path(error.absolute_path), "code": "schema_" + str(error.validator)})
                if len(errors) == 20:
                    break
            if errors:
                self.issues = errors
                return None
            json.dumps(candidate, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, RecursionError, UnicodeError, SchemaValidationError):
            return None
        self.issues = []
        return candidate

    def canonical_candidate(self, context, candidate: dict) -> dict | None:
        """Validate safe typed prose before the context and source checks."""
        self.issues = self.canonical_issues(candidate)
        if self.issues:
            return None
        try:
            size = len(json.dumps(candidate, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            self.issues = [{"path": [], "code": "invalid_json"}]
            return None
        if size > self._maximum_bytes:
            self.issues = [{"path": [], "code": "output_too_large"}]
            return None
        return candidate

    def canonical_issues(self, candidate: dict) -> list[dict]:
        """Identify failing fields using only trusted schema names."""
        self.unsafe_text = False
        codes = {
            "model-produced text is unsafe": "unsafe_text",
            "work and evaluation inability codes must be distinct": "verdict_code_overlap",
            "negative test references an unknown work finding": "finding_reference",
        }
        try:
            ProjectGuideCompilationResult.model_validate(candidate)
        except ValidationError as error:
            self.unsafe_text = invalid_compilation_failure_code(error) == "unsafe_text"
            return [
                {
                    "path": [part if isinstance(part, int) or part in self._fields else "<field>" for part in item["loc"][:16]],
                    "code": codes.get(str((item.get("ctx") or {}).get("error")), "canonical_constraint"),
                }
                for item in error.errors(include_input=False, include_context=True, include_url=False)[:20]
            ]
        return []
