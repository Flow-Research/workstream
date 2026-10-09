"""Normalized external-checker requests and results reject substituted lineage."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import (
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    RESULT_SCHEMA_ID,
    ExternalCheckerContractError,
    ExternalCheckerFinding,
    ExternalCheckerMaterial,
    ExternalCheckerSchema,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
    make_external_checker_registration_request,
)
from tests.checkers.external.support import (
    SHA,
    execution_identity,
    registry_entry,
    registry_spec,
    schema,
)


def test_registry_spec_is_digest_pinned_and_phase_specific() -> None:
    spec = registry_spec()
    assert spec.spec_digest == canonical_json_hash(spec.model_dump(mode="json"))
    assert spec.input_schema.schema_id == PRE_SUBMIT_INPUT_SCHEMA_ID
    assert spec.output_schema.schema_id == RESULT_SCHEMA_ID

    with pytest.raises(ValidationError, match="does not match its phase"):
        spec.model_copy(
            update={"input_schema": schema("external_checker_post_submit_input")}
        ).model_validate(spec.model_copy(
            update={"input_schema": schema("external_checker_post_submit_input")}
        ))
    with pytest.raises(ValidationError, match="image_digest"):
        type(spec).model_validate(spec.model_dump() | {"image_digest": "latest"})


@pytest.mark.parametrize("reference", ["https://example.invalid/schema", "other.json#/x"])
def test_registry_schema_is_offline_and_self_contained(reference: str) -> None:
    document = {"type": "object", "$ref": reference}
    with pytest.raises(ValidationError, match="non-local reference"):
        ExternalCheckerSchema(
            schema_id="acme.configuration",
            schema_version="v1",
            document=document,
            schema_sha256=canonical_json_hash(document),
        )


def test_registration_request_digest_is_derived_and_substitution_fails() -> None:
    request = make_external_checker_registration_request(
        actor_profile_id=uuid4(),
        operation_id=uuid4(),
        registry_entry_id=new_record_id(),
        spec=registry_spec(),
    )
    with pytest.raises(ValidationError, match="digest mismatch"):
        request.model_copy(update={"registry_entry_id": uuid4()}).model_validate(
        request.model_copy(update={"registry_entry_id": new_record_id()})
    )
    with pytest.raises(ExternalCheckerContractError, match="derived"):
        make_external_checker_registration_request(
            **request.model_dump(exclude={"request_digest"}), request_digest=SHA
        )


@pytest.mark.parametrize("phase", ["pre_submit", "post_submit"])
def test_execution_request_binds_existing_phase_lineage_and_materials(phase: str) -> None:
    entry = registry_entry(phase)
    request = make_external_checker_execution_request(
        registry=entry,
        identity=execution_identity(phase),
        configuration={},
        configuration_sha256=canonical_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=canonical_json_hash({"task_version": "v3"}),
        materials=(
            ExternalCheckerMaterial(
                role="submission_archive",
                content_id=uuid4(),
                replica_id=uuid4(),
                sha256=SHA,
                byte_count=4,
                media_type="application/zip",
            ),
        ),
    )
    assert request.identity.phase == phase
    with pytest.raises(ValidationError, match="input digest mismatch"):
        request.model_copy(update={"input": {"task_version": "v4"}}).model_validate(
            request.model_copy(update={"input": {"task_version": "v4"}})
        )
    with pytest.raises(ValidationError, match="phase mismatch"):
        make_external_checker_execution_request(
            **request.model_dump(exclude={"request_digest", "identity"}),
            identity=execution_identity(
                "post_submit" if phase == "pre_submit" else "pre_submit"
            ),
        )


def test_execution_identity_does_not_accept_cross_phase_or_unknown_fields() -> None:
    value = execution_identity("pre_submit").model_dump()
    value["submission_id"] = uuid4()
    with pytest.raises(ValidationError, match="submission_id"):
        type(execution_identity("pre_submit")).model_validate(value)


def test_execution_request_rejects_duplicate_material_roles() -> None:
    material = ExternalCheckerMaterial(
        role="submission_archive",
        content_id=uuid4(),
        replica_id=uuid4(),
        sha256=SHA,
        byte_count=4,
        media_type="application/zip",
    )
    with pytest.raises(ValidationError, match="role is duplicated"):
        make_external_checker_execution_request(
            registry=registry_entry(),
            identity=execution_identity(),
            configuration={},
            configuration_sha256=canonical_json_hash({}),
            input={"task_version": "v3"},
            input_sha256=canonical_json_hash({"task_version": "v3"}),
            materials=(material, material.model_copy(update={"content_id": uuid4()})),
        )


def test_completed_and_infrastructure_results_are_closed_and_request_bound() -> None:
    request = make_external_checker_execution_request(
        registry=registry_entry(),
        identity=execution_identity(),
        configuration={},
        configuration_sha256=canonical_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=canonical_json_hash({"task_version": "v3"}),
        materials=(),
    )
    completed = make_external_checker_execution_result(
        request_digest=request.request_digest,
        registry_entry_id=request.registry.registry_entry_id,
        registry_entry_digest=request.registry.entry_digest,
        phase=request.identity.phase,
        outcome="completed",
        verdict="failed",
        findings=(
            ExternalCheckerFinding(
                code="archive.unsafe_path",
                level="error",
                message="archive contains an unsafe path",
                path="../escape",
            ),
        ),
        infrastructure_failure_code=None,
    )
    completed.validate_request(request)
    with pytest.raises(ExternalCheckerContractError, match="request mismatch"):
        completed.model_copy(update={"registry_entry_id": uuid4()}).validate_request(
            request
        )
    with pytest.raises(ValidationError, match="disagree"):
        make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase="pre_submit",
            outcome="completed",
            verdict="passed",
            findings=completed.findings,
            infrastructure_failure_code=None,
        )

    unavailable = make_external_checker_execution_result(
        request_digest=request.request_digest,
        registry_entry_id=request.registry.registry_entry_id,
        registry_entry_digest=request.registry.entry_digest,
        phase="pre_submit",
        outcome="infrastructure_failed",
        verdict=None,
        findings=(),
        infrastructure_failure_code="implementation_unavailable",
    )
    unavailable.validate_request(request)
    with pytest.raises(ValidationError):
        make_external_checker_execution_result(
            **unavailable.model_dump(exclude={"result_digest", "infrastructure_failure_code"}),
            infrastructure_failure_code="network_error",
        )

    oversized_findings = tuple(
        ExternalCheckerFinding(
            code=f"archive.finding_{index}",
            level="warning",
            message="x" * 4096,
        )
        for index in range(20)
    )
    with pytest.raises(ValidationError, match="result is too large"):
        make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase="pre_submit",
            outcome="completed",
            verdict="passed",
            findings=oversized_findings,
            infrastructure_failure_code=None,
        )
