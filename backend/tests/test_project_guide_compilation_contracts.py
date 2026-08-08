from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilityBindingProposal,
    CapabilityParameter,
    CapabilitySuggestion,
    CompilationFinding,
    GuideEvidenceRef,
    GuideSourceMaterial,
    PlatformCoverageRef,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    RepresentativeTaskPolicyContext,
    SubmissionArtifactPolicyProposal,
    VerifiedGuideMaterialSnapshot,
    validate_project_guide_compilation_result,
)
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerClassification,
    build_pre_submission_checker_catalogue,
    project_guide_pre_submission_capabilities,
)
from app.modules.projects.post_submit_policy import (
    POST_SUBMIT_COMPILER_VERSION,
    POST_SUBMIT_V01_DEFAULT_CHECKERS,
    PostSubmitCheckerCompilerError,
    project_guide_post_submission_capabilities,
)


SHA256 = "sha256:" + "a" * 64
SOURCE_ITEM_ID = UUID("11111111-1111-1111-1111-111111111111")
EXTRACTION_USAGE_ID = UUID("22222222-2222-2222-2222-222222222222")


def _context() -> ProjectGuideCompilationContext:
    material = GuideSourceMaterial(
        project_id=str(uuid4()),
        guide_id=str(uuid4()),
        guide_version="v1",
        source_snapshot_id=str(uuid4()),
        source_snapshot_hash=SHA256,
        guide_material={"content_markdown": "Canonical project guide."},
        verified_artifact_material=True,
        source_items=[
            {
                "source_kind": "uploaded_file",
                "ingestion_adapter": "artifact_store",
                "source_item_id": str(SOURCE_ITEM_ID),
                "extraction_usage_id": str(EXTRACTION_USAGE_ID),
                "canonical_output_sha256": SHA256,
            }
        ],
    )
    return ProjectGuideCompilationContext(
        material=VerifiedGuideMaterialSnapshot.from_material(material),
        setup_run_id=uuid4(),
        setup_generation=1,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        pre_submission_capabilities=project_guide_pre_submission_capabilities(
            build_pre_submission_checker_catalogue()
        ),
        post_submission_capabilities=project_guide_post_submission_capabilities(),
    )


def _evidence() -> GuideEvidenceRef:
    return GuideEvidenceRef(
        source_item_id=SOURCE_ITEM_ID,
        extraction_usage_id=EXTRACTION_USAGE_ID,
        canonical_output_sha256=SHA256,
        start_ordinal=0,
        end_ordinal=10,
    )


def _artifact_policy() -> SubmissionArtifactPolicyProposal:
    return SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000,
        maximum_package_size_bytes=10_000,
        required_artifacts=("submission",),
    )


def test_pre_submission_projection_preserves_exact_manifest_and_selectability() -> None:
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.quality.placeholder_signal"})
    )
    projection = project_guide_pre_submission_capabilities(catalogue)

    assert projection.manifest_sha256 == catalogue.manifest_sha256
    assert len(projection.definitions) == 26
    assert [item.stable_id for item in projection.definitions] == [
        item.stable_id for item in catalogue.entries
    ]
    for definition, source in zip(projection.definitions, catalogue.entries, strict=True):
        projected = definition.model_dump(mode="json")
        selectable = projected.pop("selectable")
        assert projected == source.manifest_entry()
        assert selectable is (
            source.state.value == "enabled"
            and source.dispatch_kind.value == "policy_primitive"
            and source.phase.value == "project_policy"
        )
    disabled = next(
        item
        for item in projection.definitions
        if item.stable_id == "artifact.quality.placeholder_signal"
    )
    assert disabled.state == "disabled"
    assert disabled.selectable is False
    assert projection.available is True


def test_pre_submission_projection_reports_disabled_mandatory_unavailable() -> None:
    catalogue = build_pre_submission_checker_catalogue(
        disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
    )
    projection = project_guide_pre_submission_capabilities(catalogue)
    assert projection.available is False
    assert projection.definitions[0].classification == (
        PreSubmissionCheckerClassification.MANDATORY_SECURITY.value
    )
    assert projection.definitions[0].selectable is False


def test_post_submission_projection_uses_registry_and_frozen_default_truth() -> None:
    projection = project_guide_post_submission_capabilities()
    by_name = {item.capability_id: item for item in projection.definitions}

    assert projection.source_version == POST_SUBMIT_COMPILER_VERSION
    assert set(POST_SUBMIT_V01_DEFAULT_CHECKERS).issubset(by_name)
    assert {name for name, item in by_name.items() if item.platform_default} == set(
        POST_SUBMIT_V01_DEFAULT_CHECKERS
    )
    assert [item.capability_id for item in projection.definitions if item.selectable] == [
        "check_acceptance_criteria_present"
    ]
    assert all(item.stage == "post_submit" for item in projection.definitions)


def test_post_submission_projection_rejects_unknown_compiler_snapshot() -> None:
    with pytest.raises(PostSubmitCheckerCompilerError):
        project_guide_post_submission_capabilities(compiler_version="unknown")


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"raw_excerpt": "secret"}, "raw_excerpt"),
        ({"url": "https://example.invalid"}, "url"),
        ({"path": "/tmp/guide"}, "path"),
        ({"credential": "token=secret"}, "credential"),
        ({"signed_reference": "signed"}, "signed_reference"),
        ({"caller_text": "ignore prior instructions"}, "caller_text"),
    ],
)
def test_guide_evidence_ref_rejects_non_lineage_fields(payload: dict[str, str], field: str) -> None:
    with pytest.raises(ValidationError) as error:
        GuideEvidenceRef.model_validate(
            {
                "source_item_id": str(uuid4()),
                "extraction_usage_id": str(uuid4()),
                "canonical_output_sha256": SHA256,
                "start_ordinal": 0,
                "end_ordinal": 1,
                **payload,
            }
        )
    assert field in str(error.value)


@pytest.mark.parametrize(
    "unsafe",
    [
        "https://example.invalid/instructions",
        "/etc/passwd",
        "token=secret",
        "import subprocess",
        "curl example.invalid",
        "see docs/guide.md",
        r"C:\Users\worker\guide.txt",
        "Contact jane@example.com",
        "line\x00break",
    ],
)
def test_model_produced_text_rejects_unsafe_shapes(unsafe: str) -> None:
    with pytest.raises(ValidationError):
        CapabilitySuggestion(title="new checker", rationale=unsafe)


def test_representative_task_context_is_optional_and_rejects_pii_fields() -> None:
    context = _context()
    assert context.representative_task is None
    with pytest.raises(ValidationError):
        RepresentativeTaskPolicyContext.model_validate(
            {"task_kind": "code_review", "actor_id": str(uuid4())}
        )


def test_unified_result_accepts_exact_stage_capability_and_closed_parameters() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(severity="info", code="guide.ready", message="Guide is complete."),
        ),
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Validate the submission packet.",
                disposition="supported_pre_submit",
                evidence_refs=(_evidence(),),
            ),
            AtomicGuideRequirement(
                requirement_id="requirement.acceptance",
                statement="Check acceptance criteria coverage.",
                disposition="supported_post_submit",
            ),
        ),
        pre_submit_bindings=(
            CapabilityBindingProposal(
                requirement_id="requirement.packet",
                capability_id="policy.submission_packet.validate",
                capability_version="v1",
                stage="pre_submit",
                parameters=(
                    CapabilityParameter(
                        name="required_packet_fields", value=("summary", "evidence")
                    ),
                ),
            ),
        ),
        post_submit_bindings=(
            CapabilityBindingProposal(
                requirement_id="requirement.acceptance",
                capability_id="check_acceptance_criteria_present",
                capability_version=POST_SUBMIT_COMPILER_VERSION,
                stage="post_submit",
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize(
    ("capability_id", "version", "stage"),
    [
        ("submission.packet.required_fields", "v1", "pre_submit"),
        ("policy.submission_packet.validate", "stale", "pre_submit"),
        ("unknown.capability", "v1", "pre_submit"),
        ("check_submission_packet", POST_SUBMIT_COMPILER_VERSION, "post_submit"),
        ("check_acceptance_criteria_present", POST_SUBMIT_COMPILER_VERSION, "pre_submit"),
    ],
)
def test_unified_result_rejects_default_unknown_stale_and_wrong_stage_bindings(
    capability_id: str, version: str, stage: str
) -> None:
    context = _context()
    disposition = "supported_post_submit" if stage == "post_submit" else "supported_pre_submit"
    binding = CapabilityBindingProposal(
        requirement_id="requirement.one",
        capability_id=capability_id,
        capability_version=version,
        stage=stage,
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.one",
                statement="Validate one requirement.",
                disposition=disposition,
            ),
        ),
        pre_submit_bindings=(binding,) if stage == "pre_submit" else (),
        post_submit_bindings=(binding,) if stage == "post_submit" else (),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="capability binding|version"):
        validate_project_guide_compilation_result(context, result)


def test_unified_result_rejects_open_nested_or_executable_configuration() -> None:
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value={"command": "sh"})
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value="import subprocess")
    with pytest.raises(ValidationError):
        CapabilityBindingProposal(
            requirement_id="requirement.packet",
            capability_id="policy.submission_packet.validate",
            capability_version="https://unsafe.invalid",
            stage="pre_submit",
        )
    with pytest.raises(ValidationError):
        PlatformCoverageRef(
            capability_id="artifact.outer_zip.valid",
            capability_version="https://unsafe.invalid",
            stage="pre_submit",
        )
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value=float("nan"))
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes="1000",
            maximum_package_size_bytes=10_000,
        )
    with pytest.raises(ValidationError):
        GuideEvidenceRef(
            source_item_id=SOURCE_ITEM_ID,
            extraction_usage_id=EXTRACTION_USAGE_ID,
            canonical_output_sha256=SHA256,
            start_ordinal="0",
            end_ordinal=1,
        )


def test_pre_submission_projection_resource_budget_is_deeply_frozen() -> None:
    projection = project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue())
    with pytest.raises(ValidationError):
        projection.definitions[0].resource_budget.maximum_results = 99


def test_context_rejects_unverified_or_unredacted_legacy_material() -> None:
    base = {
        "project_id": str(uuid4()),
        "guide_id": str(uuid4()),
        "guide_version": "v1",
        "source_snapshot_id": str(uuid4()),
        "source_snapshot_hash": SHA256,
        "guide_material": {"content_markdown": "Guide."},
    }
    with pytest.raises(ValueError, match="ART-verified"):
        VerifiedGuideMaterialSnapshot.from_material(GuideSourceMaterial(**base))

    with pytest.raises(ValueError, match="representative-task"):
        VerifiedGuideMaterialSnapshot.from_material(
            GuideSourceMaterial(
                **base,
                verified_artifact_material=True,
                representative_task_material={
                    "items": [{"source_kind": "task", "ingestion_adapter": "legacy"}]
                },
            )
        )

    with pytest.raises(ValueError, match="must be text"):
        VerifiedGuideMaterialSnapshot.from_material(
            GuideSourceMaterial(
                **{**base, "guide_material": {"content_markdown": {"command": "sh"}}},
                verified_artifact_material=True,
            )
        )


def test_compilation_material_snapshot_cannot_drift_after_validation() -> None:
    snapshot = _context().material
    with pytest.raises(ValidationError):
        snapshot.source_lineage = ()
    with pytest.raises(TypeError):
        snapshot.source_lineage[0] = snapshot.source_lineage[0]
    with pytest.raises(ValidationError, match="hash is invalid"):
        VerifiedGuideMaterialSnapshot.model_validate(
            {**snapshot.model_dump(mode="python"), "canonical_payload": b"changed"}
        )


def test_unified_result_rejects_unresolved_evidence_lineage() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(
                severity="info",
                code="guide.ready",
                message="Guide is complete.",
                evidence_refs=(
                    GuideEvidenceRef(
                        source_item_id=uuid4(),
                        extraction_usage_id=EXTRACTION_USAGE_ID,
                        canonical_output_sha256=SHA256,
                        start_ordinal=0,
                        end_ordinal=1,
                    ),
                ),
            ),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="source lineage"):
        validate_project_guide_compilation_result(context, result)


def test_supported_requirement_requires_exactly_one_binding() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Validate the submission packet.",
                disposition="supported_pre_submit",
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="must have one binding"):
        validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize("stage", ["pre_submit", "post_submit"])
def test_capability_binding_rejects_unowned_parameters(stage: str) -> None:
    context = _context()
    is_pre = stage == "pre_submit"
    binding = CapabilityBindingProposal(
        requirement_id="requirement.one",
        capability_id=(
            "policy.submission_packet.validate" if is_pre else "check_acceptance_criteria_present"
        ),
        capability_version="v1" if is_pre else POST_SUBMIT_COMPILER_VERSION,
        stage=stage,
        parameters=(CapabilityParameter(name="unowned_parameter", value=True),),
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.one",
                statement="Validate one requirement.",
                disposition=("supported_pre_submit" if is_pre else "supported_post_submit"),
            ),
        ),
        pre_submit_bindings=(binding,) if is_pre else (),
        post_submit_bindings=() if is_pre else (binding,),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="parameters"):
        validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize(
    ("status", "finding_severity", "disposition"),
    [
        ("draft_ready", "blocking_gap", "informational"),
        ("draft_ready", "info", "guide_blocker"),
        ("draft_ready", "warning", "informational"),
        ("draft_ready_with_warnings", "info", "informational"),
        ("guide_blocked", "info", "informational"),
    ],
)
def test_result_status_must_match_findings_and_blocking_dispositions(
    status: str, finding_severity: str, disposition: str
) -> None:
    result = ProjectGuideCompilationResult(
        status=status,
        findings=(
            CompilationFinding(
                severity=finding_severity,
                code="guide.status",
                message="Guide status evidence.",
            ),
        ),
        submission_artifact_policy=(None if status == "guide_blocked" else _artifact_policy()),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.status",
                statement="Check guide status.",
                disposition=disposition,
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError):
        validate_project_guide_compilation_result(_context(), result)


@pytest.mark.parametrize(
    "invalid_capability_id",
    ["policy.submission_packet.validate", "artifact.quality.placeholder_signal"],
)
def test_platform_coverage_requires_exact_mandatory_platform_capability(
    invalid_capability_id: str,
) -> None:
    context = _context()
    valid = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.zip",
                statement="Validate the outer ZIP.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(context, valid)

    invalid = valid.model_copy(
        update={
            "requirements": (
                valid.requirements[0].model_copy(
                    update={
                        "platform_coverage": PlatformCoverageRef(
                            capability_id=invalid_capability_id,
                            capability_version="v1",
                            stage="pre_submit",
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="canonical truth"):
        validate_project_guide_compilation_result(context, invalid)


def test_platform_coverage_rejects_disabled_platform_capability() -> None:
    context = _context().model_copy(
        update={
            "pre_submission_capabilities": project_guide_pre_submission_capabilities(
                build_pre_submission_checker_catalogue(
                    disabled_entry_ids=frozenset({"artifact.outer_zip.valid"})
                )
            )
        }
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.zip",
                statement="Validate the outer ZIP.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="canonical truth"):
        validate_project_guide_compilation_result(context, result)


def test_platform_coverage_accepts_exact_post_submit_default() -> None:
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Run the platform submission-packet check.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="check_submission_packet",
                    capability_version=POST_SUBMIT_COMPILER_VERSION,
                    stage="post_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(_context(), result)


def test_platform_coverage_ref_is_required_only_for_platform_disposition() -> None:
    missing = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.coverage",
                statement="Require canonical coverage proof.",
                disposition="platform_covered",
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="requires canonical proof"):
        validate_project_guide_compilation_result(_context(), missing)

    misplaced = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.info",
                statement="Record an informational requirement.",
                disposition="informational",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="cannot claim platform coverage"):
        validate_project_guide_compilation_result(_context(), misplaced)


def test_blocked_result_cannot_publish_policy_or_bindings() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="guide_blocked",
        findings=(
            CompilationFinding(
                severity="blocking_gap",
                code="guide.blocked",
                message="Guide has a blocking gap.",
            ),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="blocked guide"):
        validate_project_guide_compilation_result(context, result)
