"""Normalized external-checker requests and results reject substituted lineage."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import (
    MAX_SCHEMA_BYTES,
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    RESULT_SCHEMA_ID,
    ExternalCheckerContractError,
    ExternalCheckerFinding,
    ExternalCheckerRegistrationCommand,
    PreSubmitExternalCheckerMaterial,
    ExternalCheckerSchema,
    external_checker_registration_request_digest,
    external_checker_json_hash,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from tests.checkers.external.support import (
    SHA,
    execution_identity,
    execution_material,
    registry_entry,
    registry_spec,
    schema,
)


def test_registry_spec_is_digest_pinned_and_phase_specific() -> None:
    spec = registry_spec()
    assert spec.spec_digest == external_checker_json_hash(spec.model_dump(mode="json"))
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


def test_registry_canonical_hash_uses_database_numeric_encoding() -> None:
    assert external_checker_json_hash({"minimum": 1e-6}) == (
        "sha256:e084f70f19f83edfde8a2b57061cd7734340a5be2e7d127e3b73c090556478a7"
    )


@pytest.mark.parametrize(
    "value",
    (
        {"unsafe\x00key": "value"},
        {"safe": "unsafe\x00value"},
    ),
)
def test_registry_canonical_json_rejects_jsonb_untranslatable_nul(value: dict) -> None:
    with pytest.raises(ExternalCheckerContractError, match="not canonical JSON"):
        external_checker_json_hash(value)


def test_registry_canonical_json_accepts_other_unicode_controls() -> None:
    value = {"snowman-☃\n": "line\n\t\bsnowman:☃"}
    assert external_checker_json_hash(value).startswith("sha256:")


def test_schema_size_uses_the_canonical_persisted_representation() -> None:
    overhead = len('{"description":"","type":"object"}'.encode())
    document = {"type": "object", "description": "x" * (MAX_SCHEMA_BYTES - overhead)}
    accepted = ExternalCheckerSchema(
        schema_id="acme.boundary",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    assert accepted.document == document
    oversized = document | {"description": document["description"] + "x"}
    with pytest.raises(ValidationError, match="schema is too large"):
        ExternalCheckerSchema(
            schema_id="acme.boundary",
            schema_version="v1",
            document=oversized,
            schema_sha256=external_checker_json_hash(oversized),
        )


@pytest.mark.parametrize("reference", ["https://example.invalid/schema", "other.json#/x"])
def test_registry_schema_is_offline_and_self_contained(reference: str) -> None:
    document = {"type": "object", "$ref": reference}
    with pytest.raises(ValidationError, match="non-local reference"):
        ExternalCheckerSchema(
            schema_id="acme.configuration",
            schema_version="v1",
            document=document,
            schema_sha256=external_checker_json_hash(document),
        )


def test_registration_request_digest_binds_server_selected_uuid() -> None:
    command = ExternalCheckerRegistrationCommand(
        actor_profile_id=uuid4(),
        operation_id=uuid4(),
        spec=registry_spec(),
    )
    first, second = new_record_id(), new_record_id()
    assert external_checker_registration_request_digest(command, first) != (
        external_checker_registration_request_digest(command, second)
    )
    changed = command.model_copy(
        update={"spec": registry_spec("post_submit")}
    )
    assert external_checker_registration_request_digest(command, first) != (
        external_checker_registration_request_digest(changed, first)
    )
    with pytest.raises(ExternalCheckerContractError, match="UUIDv7"):
        external_checker_registration_request_digest(command, uuid4())


@pytest.mark.parametrize("phase", ["pre_submit", "post_submit"])
def test_execution_request_binds_existing_phase_lineage_and_materials(phase: str) -> None:
    entry = registry_entry(phase)
    identity = execution_identity(phase)
    request = make_external_checker_execution_request(
        registry=entry,
        identity=identity,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=external_checker_json_hash({"task_version": "v3"}),
        materials=(execution_material(identity),),
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
    identity = execution_identity()
    material = PreSubmitExternalCheckerMaterial(
        role="submission_archive",
        operation_id=identity.operation_id, source_sha256=identity.source_sha256,
            lease_id=identity.lease_id, lease_generation=identity.lease_generation,
        attempt_id=identity.attempt_id,
        attempt_request_digest=identity.attempt_request_digest,
        archive_sha256=SHA,
        archive_byte_count=4,
        semantic_manifest_sha256=SHA,
        media_type="application/zip",
    )
    with pytest.raises(ValidationError, match="role is duplicated"):
        make_external_checker_execution_request(
            registry=registry_entry(),
            identity=identity,
            configuration={},
            configuration_sha256=external_checker_json_hash({}),
            input={"task_version": "v3"},
            input_sha256=external_checker_json_hash({"task_version": "v3"}),
            materials=(material, material.model_copy(update={"archive_sha256": "sha256:" + "b" * 64})),
        )


def test_completed_and_infrastructure_results_are_closed_and_request_bound() -> None:
    identity = execution_identity()
    request = make_external_checker_execution_request(
        registry=registry_entry(),
        identity=identity,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=external_checker_json_hash({"task_version": "v3"}),
        materials=(execution_material(identity),),
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
                check_id="archive.paths",
                code="archive.unsafe_path",
                level="error",
                message="archive contains an unsafe path",
                path="src/escape.txt",
                line=3,
            ),
        ),
        infrastructure_failure_code=None,
    )
    completed.validate_request(request)
    with pytest.raises(ValidationError, match="result digest mismatch"):
        completed.model_copy(update={"result_digest": SHA}).validate_request(request)
    with pytest.raises(ValidationError, match="verdict and findings disagree"):
        completed.model_copy(update={"findings": ()}).validate_request(request)
    substituted = make_external_checker_execution_result(
        **completed.model_dump(exclude={"result_digest", "registry_entry_id"}),
        registry_entry_id=uuid4(),
    )
    with pytest.raises(ExternalCheckerContractError, match="request mismatch"):
        substituted.validate_request(request)
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

    bounded_identity = execution_identity()
    bounded_request = make_external_checker_execution_request(
        registry=registry_entry(maximum_output_bytes=256),
        identity=bounded_identity,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
        input={"task_version": "v3"},
        input_sha256=external_checker_json_hash({"task_version": "v3"}),
        materials=(execution_material(bounded_identity),),
    )
    oversized_infrastructure = make_external_checker_execution_result(
        request_digest=bounded_request.request_digest,
        registry_entry_id=bounded_request.registry.registry_entry_id,
        registry_entry_digest=bounded_request.registry.entry_digest,
        phase="pre_submit",
        outcome="infrastructure_failed",
        verdict=None,
        findings=(),
        infrastructure_failure_code="implementation_unavailable",
    )
    with pytest.raises(ExternalCheckerContractError, match="exceeds registry limit"):
        oversized_infrastructure.validate_request(bounded_request)

    oversized_findings = tuple(
        ExternalCheckerFinding(
            check_id="archive.size",
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


def test_findings_carry_check_location_and_coverage_level() -> None:
    finding = ExternalCheckerFinding(
        check_id="coverage.files",
        code="coverage.unreadable",
        level="coverage_incomplete",
        message="one file could not be evaluated",
        path="src/main.rs",
        line=12,
    )
    assert finding.model_dump(mode="json") == {
        "check_id": "coverage.files",
        "code": "coverage.unreadable",
        "level": "coverage_incomplete",
        "message": "one file could not be evaluated",
        "path": "src/main.rs",
        "line": 12,
    }
    with pytest.raises(ValidationError, match="line requires a path"):
        ExternalCheckerFinding(
            check_id="coverage.files", code="coverage.unreadable",
            level="warning", message="m", line=4,
        )
    with pytest.raises(ValidationError):
        ExternalCheckerFinding(code="coverage.unreadable", level="warning", message="m")
    with pytest.raises(ValidationError):
        ExternalCheckerFinding(
            check_id="coverage.files", code="c", level="warning", message="m",
            path="a", line=0,
        )


@pytest.mark.parametrize("path", [
    "../x", "/etc/passwd", "a//b", "a/./b", "src\\main.rs", "dir/ ", "dir/.",
    "c:/x", "line\nbreak", "bidi\u202eexe.txt", "tab\tname", "",
    "next\x85line", "para\u2029graph", "line\u2028sep",
])
def test_finding_paths_must_be_safe_relative_archive_paths(path) -> None:
    with pytest.raises(ValidationError):
        ExternalCheckerFinding(
            check_id="paths.check", code="paths.code", level="warning", message="m", path=path,
        )
    assert ExternalCheckerFinding(
        check_id="paths.check", code="paths.code", level="warning", message="m",
        path="src/naïve/main.rs",
    ).path == "src/naïve/main.rs"


@pytest.mark.parametrize("field", [
    "operation_id", "source_sha256", "lease_id", "lease_generation", "attempt_id", "attempt_request_digest",
])
def test_pre_request_binds_source_and_execution_fence(field):
    identity = execution_identity()
    material = execution_material(identity)
    value = (uuid4() if field.endswith("_id") else
             2 if field == "lease_generation" else "sha256:" + "f" * 64)
    material = material.model_copy(update={field: value})
    with pytest.raises(ValueError, match="source material identity mismatch"):
        make_external_checker_execution_request(
            registry=registry_entry(), identity=identity, configuration={},
            configuration_sha256=external_checker_json_hash({}), input={"task_version": "v3"},
            input_sha256=external_checker_json_hash({"task_version": "v3"}), materials=(material,),
        )


def test_pre_request_refuses_prepared_bundle_identity():
    identity = execution_identity()
    value = identity.model_dump() | {"prepared_generation_id": uuid4()}
    with pytest.raises(ValueError, match="prepared_generation_id"):
        type(identity).model_validate(value)


def test_post_source_custody_preserves_retained_material_and_closes_new_witness():
    import json
    from pathlib import Path
    from app.modules.checkers.api.external import PostSubmitExternalCheckerMaterial
    from app.modules.checkers.api.post_material_custody import PostSubmitArtifactCustody

    fixture = Path(__file__).resolve().parents[4] / "external_checkers/fixtures/post_request.json"
    retained = json.loads(fixture.read_text())["materials"][0]
    original = PostSubmitExternalCheckerMaterial.model_validate_json(json.dumps(retained))
    assert original.model_dump(mode="json") == retained
    source = {k: v for k, v in retained.items() if not k.startswith("verification_")}
    source.update(source_operation_id=str(new_record_id()), accepted_source_sha256=SHA,
                  acceptance_receipt_sha256="sha256:" + "b" * 64)
    material = PostSubmitExternalCheckerMaterial.model_validate_json(json.dumps(source))
    assert material.model_dump(mode="json") == source
    assert PostSubmitExternalCheckerMaterial.model_validate_json(material.model_dump_json()) == material
    witness = {k: v for k, v in source.items() if k in PostSubmitArtifactCustody.model_fields}
    assert PostSubmitArtifactCustody.model_validate_json(json.dumps(witness)).model_dump(mode="json") == witness
    for field in witness:
        with pytest.raises(ValidationError):
            PostSubmitExternalCheckerMaterial.model_validate_json(json.dumps({k: v for k, v in source.items() if k != field}))
    for field in ("verification_receipt_id", "verification_job_id", "verification_generation"):
        with pytest.raises(ValidationError):
            PostSubmitExternalCheckerMaterial.model_validate_json(json.dumps(source | {field: retained[field]}))


def test_source_predecessor_custody_keeps_exact_witness_on_roundtrip():
    from app.modules.checkers.api.evaluation_context import PostSubmitPredecessorCustody
    custody = PostSubmitPredecessorCustody(
        submission_id=new_record_id(), submission_version=1, content_sha256=SHA,
        byte_count=4, semantic_manifest_sha256=SHA, admission_id=new_record_id(),
        binding_id=new_record_id(), content_id=new_record_id(), replica_id=new_record_id(),
        evidence_id=new_record_id(), namespace_fingerprint=SHA, semantic_manifest_id=new_record_id(),
        source_operation_id=new_record_id(), accepted_source_sha256=SHA, acceptance_receipt_sha256=SHA,
    )
    body = custody.model_dump(mode="json")
    assert not any(key.startswith("verification_") for key in body)
    assert body["source_operation_id"] == str(custody.source_operation_id)
    assert PostSubmitPredecessorCustody.model_validate_json(custody.model_dump_json()) == custody
