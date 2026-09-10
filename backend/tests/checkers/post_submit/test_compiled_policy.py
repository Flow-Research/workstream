"""Canonical compiler custody, closed-body rejection and policy classification proof."""

import json

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api import CompiledPostSubmitPolicy
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.post_submit_policy import build_project_post_submit_checker_spec, compile_project_post_submit_checker_spec, parse_locked_post_submit_checker_policy_body
from tests.checkers.post_submit.support import PROJECT, altered_catalogue, catalogue, request


def compile_selection(*, required=(), warning=()):
    return compile_project_post_submit_checker_spec(
        project_id=str(PROJECT),
        guide_version="v1",
        spec=build_project_post_submit_checker_spec(
            project_id=str(PROJECT),
            guide_version="v1",
            required_checkers=list(required),
            warning_checkers=list(warning),
        ),
    )


def parse(body, *, digest=None):
    return parse_locked_post_submit_checker_policy_body(
        body,
        project_id=str(PROJECT),
        guide_version="v1",
        policy_hash=canonical_json_hash(body) if digest is None else digest,
    )


def test_canonical_compile_parse_and_derived_lists():
    policy = request().policy
    assert parse(policy.policy_body) == policy
    assert policy.entries[1].implementation_version == "workstream-structural"
    assert len(policy.entries) == 9
    assert len(compile_selection().entries) == 8
    warning = compile_selection(warning=("check_acceptance_criteria_present",))
    assert warning.entries[-1].classification == "project_warning"
    assert warning.warning_checkers == ["check_acceptance_criteria_present"]
    assert warning.required_checkers == []
    assert policy.required_checkers == ["check_acceptance_criteria_present"]
    assert policy.execution_checkers == policy.default_checkers + policy.required_checkers


@pytest.mark.parametrize(
    "required,warning",
    [
        (("unknown",), ()),
        (("check_submission_packet",), ()),
        ((), ("check_submission_packet",)),
        (("check_acceptance_criteria_present",), ("check_acceptance_criteria_present",)),
        (("check_acceptance_criteria_present", "check_acceptance_criteria_present"), ()),
    ],
)
def test_compiler_rejects_unavailable_or_conflicting_project_selection(required, warning):
    with pytest.raises(
        ValueError, match="selection is unavailable|conflicting|duplicate|warning-only"
    ):
        compile_selection(required=required, warning=warning)


@pytest.mark.parametrize("index", (0, 8))
def test_disabled_default_or_selected_definition_rejects(index):
    policy = request().policy
    snapshot = altered_catalogue(index=index, state="disabled")
    body = policy.policy_body
    body["catalogue_manifest_sha256"] = snapshot.manifest_sha256
    with pytest.raises(ValueError, match="definition is unavailable"):
        CompiledPostSubmitPolicy.model_validate_json(json.dumps(body)).validate_catalogue(snapshot)
    # Self-consistent metadata still cannot replace the installed compiler catalogue.
    with pytest.raises(ValueError, match="catalogue hash mismatch"):
        parse(body)


@pytest.mark.parametrize(
    "change,match",
    [
        ("hash", "policy hash is invalid"),
        ("catalogue", "catalogue hash mismatch"),
        ("implementation", "implementation version mismatch"),
        ("omit", "omits mandatory"),
        ("default", "classification mismatch"),
        ("order", "order or dependency"),
        ("repeat", "duplicate entries"),
        ("severity", "blocking severities"),
        ("configuration", "Extra inputs"),
        ("checker", "capability or version is unavailable"),
        ("schema_version", "Input should be"),
        ("compiler_version", "Input should be"),
        ("catalogue_id", "Input should be"),
        ("catalogue_source_version", "Input should be"),
        ("catalogue_schema_version", "Input should be"),
    ],
)
def test_recomputed_hash_cannot_hide_invalid_current_body(change, match):
    body = request().policy.policy_body
    if change == "hash":
        with pytest.raises(ValueError, match=match):
            parse(body, digest="sha256:" + "0" * 64)
        return
    if change == "catalogue":
        body["catalogue_manifest_sha256"] = "sha256:" + "0" * 64
    elif change == "implementation":
        body["entries"][1]["implementation_version"] = "unsupported"
    elif change == "omit":
        del body["entries"][0]
    elif change == "default":
        body["entries"][0]["classification"] = "project_required"
    elif change == "order":
        body["entries"][0], body["entries"][1] = body["entries"][1], body["entries"][0]
    elif change == "repeat":
        body["entries"][1] = body["entries"][0]
    elif change == "severity":
        body["blocking_severities"] = ["low", "medium"]
    elif change == "configuration":
        body["entries"][0]["configuration"] = {"skip": True}
    elif change == "checker":
        body["entries"][0]["checker_id"] = "unknown"
    else:
        body[change] = "unsupported"
    with pytest.raises(ValueError, match=match):
        parse(body)


def test_agent_projection_is_exact_current_catalogue():
    projection = current_post_submit_catalogue()
    assert projection.model_dump(mode="json") == catalogue().model_dump(mode="json")
    corrupted = projection.model_dump()
    corrupted["definitions"][0]["state"] = "disabled"
    with pytest.raises(ValidationError, match="hash mismatch"):
        type(projection).model_validate(corrupted)


def test_sparse_policy_with_recomputed_hash_has_no_reader():
    policy = request().policy
    body = {
        "schema_version": "post_submit_checker_policy",
        "compiler_version": "workstream-post-submit-compiler",
        "project_id": str(PROJECT),
        "guide_version": "v1",
        "default_checkers": policy.default_checkers,
        "required_checkers": policy.required_checkers,
        "warning_checkers": [],
        "execution_checkers": policy.execution_checkers,
        "blocking_severities": ["critical", "high"],
    }
    with pytest.raises(ValidationError, match="Extra inputs"):
        parse(body)


@pytest.mark.parametrize("field", ("required_checkers", "warning_checkers", "blocking_severities"))
def test_each_persisted_sidecar_must_equal_canonical_body(field):
    policy = request().policy
    values = dict(
        required_checkers=policy.required_checkers,
        warning_checkers=policy.warning_checkers,
        blocking_severities=list(policy.blocking_severities),
    )
    policy.validate_sidecars(**values)
    values[field] = [*values[field], "crossed"]
    with pytest.raises(ValueError, match="summaries disagree"):
        policy.validate_sidecars(**values)
