"""Approved bindings resolve to exact immutable external registry facts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.identifiers import new_record_id
from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    CapabilityParameter,
    CheckInfrastructureFailure,
    CheckRuntimeDependency,
    CheckSpecification,
    CompilationStage,
    PostSubmissionBindingProposal,
    PreSubmissionBindingProposal,
    RequirementDisposition,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    external_checker_json_hash,
    ExternalCheckerRegistryUnavailable,
)
from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external_policy import (
    FORGE_FACTS_VERSION_KEY,
    SELECTED_POST_FORGE_FACTS_BUDGET_MS,
    ExternalCheckerPolicyError,
    ForgeFactsSelection,
    LockedExternalCheckerBinding,
    LockedExternalPostSubmitPolicy,
    LockedWorkstreamDefault,
    MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS,
    SELECTED_POST_MATERIALIZATION_BUDGET_MS,
    compile_external_checker_policies,
    selected_forge_facts,
    selected_post_submit_execution_budget_ms,
    selected_pre_submit_execution_budget_ms,
)
from app.modules.model_usage.api import (
    ModelGenerationSettings,
    ModelPricing,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)
from app.modules.checkers.api.external import EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
from app.modules.artifacts.preparation import ArtifactPreparationLimits
from tests.checkers.external.support import registry_spec
from tests.projects.guide_compilation.helpers import result, valid_specification


def _entry(
    capability_id: str,
    phase: str,
    configuration_schema=None,
    *,
    deadline_ms: int | None = None,
) -> ExternalCheckerRegistryEntry:
    changes = {"capability_id": capability_id}
    if configuration_schema is not None:
        changes["configuration_schema"] = configuration_schema
    spec = registry_spec(phase).model_copy(update=changes)
    if deadline_ms is not None:
        spec = spec.model_copy(
            update={"resources": spec.resources.model_copy(update={"deadline_ms": deadline_ms})}
        )
    # Revalidate after changing one digest-bound specification field.
    spec = type(spec).model_validate(spec.model_dump())
    return ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=new_record_id(),
        entry_digest=spec.spec_digest,
        registration_operation_id=uuid4(),
        registered_by_actor_profile_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        created_at=datetime.now(UTC),
    )


class _Registry:
    def __init__(self, entries):
        self.entries = {
            (entry.capability_id, entry.capability_version, entry.phase): entry for entry in entries
        }
        self.calls = []

    async def read_identity(self, **identity):
        self.calls.append(identity)
        try:
            return self.entries[
                (
                    identity["capability_id"],
                    identity["capability_version"],
                    identity["phase"],
                )
            ]
        except KeyError as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc


class _Profiles:
    def __init__(self, profile):
        self.profile = profile
        self.calls = []

    async def read_exact(self, selector, **scope):
        self.calls.append((selector, scope))
        return self.profile


def _model_configuration_schema() -> ExternalCheckerSchema:
    document = {
        "type": "object",
        "properties": {
            "model_profile_id": {"type": "string"},
            "model_profile_version": {"type": "integer"},
            "model_profile_digest": {"type": "string"},
        },
        "required": [
            "model_profile_id",
            "model_profile_version",
            "model_profile_digest",
        ],
        "additionalProperties": False,
    }
    return ExternalCheckerSchema(
        schema_id="acme.model.configuration",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _model_profile(project_id, entry) -> ProjectModelProfile:
    profile_id = new_record_id()
    pricing = ModelPricing(
        pricing_policy_id=new_record_id(),
        pricing_policy_version=1,
        pricing_policy_digest=external_checker_json_hash({"pricing": "fixed"}),
        uncached_input_nanodollars_per_token=3,
        cached_input_nanodollars_per_token=1,
        output_nanodollars_per_token=7,
    )
    spec = ProjectModelProfileSpec(
        project_id=project_id,
        profile_version=1,
        provider="openai_responses",
        api="responses.v1",
        model_snapshot="gpt-example-2026-10-01",
        settings=ModelGenerationSettings(reasoning_effort="medium", text_verbosity="low"),
        maximum_request_bytes=10_000,
        maximum_output_bytes=4_000,
        maximum_response_bytes=30_000,
        maximum_input_tokens=100,
        maximum_output_tokens=50,
        maximum_calls=1,
        maximum_total_request_bytes=10_000,
        maximum_total_response_bytes=30_000,
        maximum_total_input_tokens=100,
        maximum_total_output_tokens=50,
        allowed_tools=(),
        maximum_tool_calls=0,
        maximum_tool_output_bytes=0,
        deadline_ms=30_000,
        pricing=pricing,
    )
    return ProjectModelProfile(
        operation_id=uuid4(),
        actor_profile_id=uuid4(),
        spec=spec,
        profile_digest=external_checker_json_hash(spec.model_dump(mode="json")),
        profile_id=profile_id,
        authorization_evidence_id=uuid4(),
        created_at=datetime.now(UTC),
    )


def _proposal():
    pre = AtomicGuideRequirement(
        requirement_id="safe_archive",
        statement="Inspect the delivered archive.",
        disposition=RequirementDisposition.SUPPORTED_PRE_SUBMIT,
    )
    post = AtomicGuideRequirement(
        requirement_id="quality_review",
        statement="Evaluate the submitted work.",
        disposition=RequirementDisposition.SUPPORTED_POST_SUBMIT,
    )
    return result().model_copy(
        update={
            "requirements": (pre, post),
            "pre_submit_bindings": (
                PreSubmissionBindingProposal(
                    requirement_id=pre.requirement_id,
                    capability_id="acme.safe_archive",
                    capability_version="v1.2.3",
                    stage=CompilationStage.PRE_SUBMIT,
                ),
            ),
            "post_submit_bindings": (
                PostSubmissionBindingProposal(
                    requirement_id=post.requirement_id,
                    capability_id="acme.quality_review",
                    capability_version="v1.2.3",
                    stage=CompilationStage.POST_SUBMIT,
                ),
            ),
        }
    )


def _model_proposal():
    proposal = _proposal()
    model_specification = CheckSpecification.model_validate(
        valid_specification().model_dump(mode="json")
        | {
            "evaluation_method": "model_evaluation",
            "execution_mode": "background",
            "stage_rationale": "Model review runs after immutable submission creation.",
            "runtime_dependencies": (
                CheckRuntimeDependency(
                    dependency_id="model_runtime",
                    kind="model_service",
                    provisioning="model_proxy",
                    purpose="Bounded trusted model access for the project image.",
                    unavailable_code="implementation_unavailable",
                ),
            ),
            "infrastructure_failures": (
                *valid_specification().infrastructure_failures,
                CheckInfrastructureFailure(
                    code="implementation_unavailable",
                    condition="The trusted model service is unavailable.",
                ),
            ),
        }
    )
    post = proposal.requirements[1].model_copy(update={"check_specification": model_specification})
    return proposal.model_copy(update={"requirements": (proposal.requirements[0], post)})


@pytest.mark.asyncio
async def test_compilation_locks_exact_phase_registry_entries_and_default():
    entries = (
        _entry("acme.safe_archive", "pre_submit"),
        _entry("acme.quality_review", "post_submit"),
    )
    registry = _Registry(entries)

    pre, post = await compile_external_checker_policies(_proposal(), registry)

    assert pre.workstream_default.checker_id == "workstream.default"
    assert [(item.requirement_id, item.registry.registry_entry_id) for item in pre.entries] == [
        ("safe_archive", entries[0].registry_entry_id)
    ]
    assert [(item.requirement_id, item.registry.registry_entry_id) for item in post.entries] == [
        ("quality_review", entries[1].registry_entry_id)
    ]
    assert pre.entries[0].configuration == {}
    assert post.entries[0].configuration == {}
    assert [call["phase"] for call in registry.calls] == ["pre_submit", "post_submit"]


@pytest.mark.asyncio
async def test_model_configuration_requires_exact_post_profile_scope():
    project_id = new_record_id()
    pre = _entry("acme.safe_archive", "pre_submit")
    post = _entry(
        "acme.quality_review",
        "post_submit",
        _model_configuration_schema(),
    )
    profile = _model_profile(project_id, post)
    profiles = _Profiles(profile)
    proposal = _model_proposal()
    binding = proposal.post_submit_bindings[0].model_copy(
        update={
            "parameters": (
                CapabilityParameter(name="model_profile_id", value=str(profile.profile_id)),
                CapabilityParameter(name="model_profile_version", value=1),
                CapabilityParameter(name="model_profile_digest", value=profile.profile_digest),
            )
        }
    )

    _, policy = await compile_external_checker_policies(
        proposal.model_copy(update={"post_submit_bindings": (binding,)}),
        _Registry((pre, post)),
        project_id=project_id,
        profiles=profiles,
    )

    assert policy.entries[0].configuration == {
        "model_profile_id": str(profile.profile_id),
        "model_profile_version": 1,
        "model_profile_digest": profile.profile_digest,
    }
    selector, scope = profiles.calls[0]
    assert selector == profile.selector
    assert scope == {
        "project_id": project_id,
    }


@pytest.mark.asyncio
async def test_isolated_execution_model_dependency_also_requires_exact_profile():
    project_id = new_record_id()
    pre = _entry("acme.safe_archive", "pre_submit")
    post = _entry(
        "acme.quality_review",
        "post_submit",
        _model_configuration_schema(),
    )
    profile = _model_profile(project_id, post)
    proposal = _model_proposal()
    specification = proposal.requirements[1].check_specification
    assert specification is not None
    specification = specification.model_copy(
        update={
            "evaluation_method": "isolated_execution",
            "runtime_dependencies": (
                CheckRuntimeDependency(
                    dependency_id="isolated_runtime",
                    kind="isolated_execution",
                    provisioning="current_runner",
                    purpose="Execute the bounded authenticated trial.",
                    unavailable_code="implementation_unavailable",
                ),
                *specification.runtime_dependencies,
            ),
        }
    )
    requirement = proposal.requirements[1].model_copy(update={"check_specification": specification})
    proposal = proposal.model_copy(update={"requirements": (proposal.requirements[0], requirement)})

    with pytest.raises(ValueError, match="model evaluation profile"):
        await compile_external_checker_policies(
            proposal,
            _Registry((pre, post)),
            project_id=project_id,
            profiles=_Profiles(profile),
        )

    binding = proposal.post_submit_bindings[0].model_copy(
        update={
            "parameters": (
                CapabilityParameter(name="model_profile_id", value=str(profile.profile_id)),
                CapabilityParameter(name="model_profile_version", value=1),
                CapabilityParameter(name="model_profile_digest", value=profile.profile_digest),
            )
        }
    )
    _, policy = await compile_external_checker_policies(
        proposal.model_copy(update={"post_submit_bindings": (binding,)}),
        _Registry((pre, post)),
        project_id=project_id,
        profiles=_Profiles(profile),
    )
    assert policy.entries[0].configuration["model_profile_id"] == str(profile.profile_id)


@pytest.mark.asyncio
async def test_model_configuration_rejects_partial_pre_and_substituted_profile():
    project_id = new_record_id()
    pre = _entry(
        "acme.safe_archive",
        "pre_submit",
        _model_configuration_schema(),
    )
    ordinary_pre = _entry("acme.safe_archive", "pre_submit")
    post = _entry(
        "acme.quality_review",
        "post_submit",
        _model_configuration_schema(),
    )
    profile = _model_profile(project_id, post)
    parameters = (
        CapabilityParameter(name="model_profile_id", value=str(profile.profile_id)),
        CapabilityParameter(name="model_profile_version", value=1),
        CapabilityParameter(name="model_profile_digest", value=profile.profile_digest),
    )
    proposal = _model_proposal()
    with pytest.raises(ValueError, match="model evaluation profile"):
        await compile_external_checker_policies(
            proposal,
            _Registry(
                (
                    ordinary_pre,
                    _entry("acme.quality_review", "post_submit"),
                )
            ),
            project_id=project_id,
            profiles=_Profiles(profile),
        )
    post_binding = proposal.post_submit_bindings[0].model_copy(update={"parameters": parameters})
    partial = post_binding.model_copy(update={"parameters": parameters[:1]})
    with pytest.raises(ValueError, match="configuration"):
        await compile_external_checker_policies(
            proposal.model_copy(update={"post_submit_bindings": (partial,)}),
            _Registry((ordinary_pre, post)),
            project_id=project_id,
            profiles=_Profiles(profile),
        )

    pre_binding = proposal.pre_submit_bindings[0].model_copy(update={"parameters": parameters})
    with pytest.raises(ValueError, match="configuration"):
        await compile_external_checker_policies(
            proposal.model_copy(update={"pre_submit_bindings": (pre_binding,)}),
            _Registry((pre, post)),
            project_id=project_id,
            profiles=_Profiles(profile),
        )

    substituted = _model_profile(new_record_id(), post)
    with pytest.raises(ValueError, match="unavailable"):
        await compile_external_checker_policies(
            proposal.model_copy(update={"post_submit_bindings": (post_binding,)}),
            _Registry((ordinary_pre, post)),
            project_id=project_id,
            profiles=_Profiles(substituted),
        )


@pytest.mark.asyncio
async def test_compilation_refuses_missing_or_wrong_phase_registry_identity():
    proposal = _proposal()
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await compile_external_checker_policies(proposal, _Registry(()))

    wrong = _entry("acme.safe_archive", "post_submit")
    with pytest.raises(ExternalCheckerRegistryUnavailable):
        await compile_external_checker_policies(proposal, _Registry((wrong,)))

    class _SubstitutedRegistry:
        async def read_identity(self, **_identity):
            return _entry("acme.substituted", "pre_submit")

    with pytest.raises(ExternalCheckerPolicyError, match="identity"):
        await compile_external_checker_policies(proposal, _SubstitutedRegistry())


@pytest.mark.asyncio
async def test_compilation_refuses_requirement_and_registry_digest_substitution():
    proposal = _proposal()
    wrong_requirement = proposal.model_copy(
        update={
            "pre_submit_bindings": (
                proposal.pre_submit_bindings[0].model_copy(
                    update={"requirement_id": "quality_review"}
                ),
            )
        }
    )
    with pytest.raises(ExternalCheckerPolicyError, match="does not cover"):
        await compile_external_checker_policies(
            wrong_requirement,
            _Registry((_entry("acme.safe_archive", "pre_submit"),)),
        )

    entry = _entry("acme.safe_archive", "pre_submit")
    corrupt = entry.model_copy(update={"entry_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="entry digest"):
        await compile_external_checker_policies(proposal, _Registry((corrupt,)))


@pytest.mark.asyncio
async def test_compilation_refuses_blocked_capability_coverage():
    proposal = _proposal().model_copy(
        update={
            "status": "guide_blocked",
            "submission_artifact_policy": None,
            "capability_suggestions": (),
        }
    )
    with pytest.raises(ExternalCheckerPolicyError, match="coverage"):
        await compile_external_checker_policies(proposal, _Registry(()))


def test_locked_default_refuses_substituted_behavior_digest():
    with pytest.raises(ValueError, match="behavior"):
        LockedWorkstreamDefault(behavior_sha256="sha256:" + "0" * 64)


@pytest.mark.asyncio
async def test_selected_pre_budget_binds_ordered_deadlines_to_art_custody():
    pre, _ = await compile_external_checker_policies(
        _proposal(),
        _Registry(
            (
                _entry("acme.safe_archive", "pre_submit"),
                _entry("acme.quality_review", "post_submit"),
            )
        ),
    )
    assert selected_pre_submit_execution_budget_ms(pre, artifact_deadline_ms=150_000) == 150_000
    with pytest.raises(ExternalCheckerPolicyError, match="exceeds ART"):
        selected_pre_submit_execution_budget_ms(pre, artifact_deadline_ms=149_999)


@pytest.mark.asyncio
async def test_selected_post_maximum_fits_default_art_custody_and_rejects_overrun():
    image_deadline = (
        MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
        - SELECTED_POST_MATERIALIZATION_BUDGET_MS
        - EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
    )
    _, policy = await compile_external_checker_policies(
        _proposal(),
        _Registry(
            (
                _entry("acme.safe_archive", "pre_submit"),
                _entry(
                    "acme.quality_review",
                    "post_submit",
                    deadline_ms=image_deadline,
                ),
            )
        ),
    )
    limits = ArtifactPreparationLimits()

    assert (
        selected_post_submit_execution_budget_ms(
            policy,
            artifact_deadline_ms=int(limits.total_deadline_seconds * 1000),
        )
        == MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
    )
    assert (
        limits.total_deadline_seconds + limits.cleanup_margin_seconds
        < limits.reservation_ttl_seconds
    )
    with pytest.raises(ExternalCheckerPolicyError, match="ART custody"):
        selected_post_submit_execution_budget_ms(
            policy,
            artifact_deadline_ms=MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS - 1,
        )

    too_slow = policy.model_copy(
        update={
            "entries": (
                policy.entries[0].model_copy(
                    update={
                        "registry": _entry(
                            "acme.quality_review",
                            "post_submit",
                            deadline_ms=image_deadline + 1,
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ExternalCheckerPolicyError, match="durable worker"):
        selected_post_submit_execution_budget_ms(too_slow)


@pytest.mark.asyncio
async def test_pre_configuration_is_schema_checked_and_locked_as_json():
    document = {
        "type": "object",
        "properties": {
            "threshold": {"type": "integer", "minimum": 1},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["threshold", "tags"],
        "additionalProperties": False,
    }
    schema = ExternalCheckerSchema(
        schema_id="acme.pre.configuration",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    registry = _Registry(
        (
            _entry("acme.safe_archive", "pre_submit", schema),
            _entry("acme.quality_review", "post_submit"),
        )
    )
    proposal = _proposal()
    parameters = (
        CapabilityParameter(name="threshold", value=3),
        CapabilityParameter(name="tags", value=("alpha", "beta")),
    )
    binding = proposal.pre_submit_bindings[0].model_copy(update={"parameters": parameters})
    configured = proposal.model_copy(update={"pre_submit_bindings": (binding,)})
    pre, _ = await compile_external_checker_policies(configured, registry)
    assert pre.entries[0].configuration == {"threshold": 3, "tags": ["alpha", "beta"]}
    assert pre.entries[0].configuration_sha256 == external_checker_json_hash(
        {"threshold": 3, "tags": ["alpha", "beta"]}
    )
    for invalid in ((), (CapabilityParameter(name="threshold", value="three"),)):
        wrong = binding.model_copy(update={"parameters": invalid})
        with pytest.raises(ValueError):
            await compile_external_checker_policies(
                proposal.model_copy(update={"pre_submit_bindings": (wrong,)}),
                registry,
            )


def test_pre_configuration_preserves_retained_empty_binding_and_rejects_duplicates():
    binding = _proposal().pre_submit_bindings[0]
    retained = {
        "requirement_id": "safe_archive",
        "capability_id": "acme.safe_archive",
        "capability_version": "v1.2.3",
        "stage": "pre_submit",
    }
    assert binding.model_dump(mode="json") == retained
    assert PreSubmissionBindingProposal.model_validate(retained).model_dump(mode="json") == retained
    duplicate = CapabilityParameter(name="threshold", value=3)
    with pytest.raises(ValueError, match="unique"):
        PreSubmissionBindingProposal.model_validate(
            retained | {"parameters": (duplicate, duplicate)}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregate", [False, True])
async def test_policy_compilation_refuses_unrunnable_post_images(aggregate: bool):
    proposal = _proposal()
    entries = [_entry("acme.safe_archive", "pre_submit")]
    if aggregate:
        binding = proposal.post_submit_bindings[0]
        requirement = next(
            item for item in proposal.requirements if item.requirement_id == binding.requirement_id
        )
        proposal = proposal.model_copy(
            update={
                "requirements": proposal.requirements
                + (requirement.model_copy(update={"requirement_id": "secondary_review"}),),
                "post_submit_bindings": proposal.post_submit_bindings
                + (
                    binding.model_copy(
                        update={
                            "requirement_id": "secondary_review",
                            "capability_id": "acme.secondary_review",
                        }
                    ),
                ),
            }
        )
        entries.extend(
            [
                _entry("acme.quality_review", "post_submit", deadline_ms=1_700_000),
                _entry("acme.secondary_review", "post_submit", deadline_ms=1_700_000),
            ]
        )
    else:
        entries.append(_entry("acme.quality_review", "post_submit", deadline_ms=3_600_000))
    with pytest.raises(ValueError, match="durable worker deadline"):
        await compile_external_checker_policies(proposal, _Registry(entries))


@pytest.mark.asyncio
async def test_policy_compilation_refuses_pre_images_exceeding_platform_custody():
    proposal = _proposal()
    binding = proposal.pre_submit_bindings[0]
    requirement = proposal.requirements[0]
    proposal = proposal.model_copy(
        update={
            "requirements": proposal.requirements
            + (requirement.model_copy(update={"requirement_id": "secondary_archive"}),),
            "pre_submit_bindings": proposal.pre_submit_bindings
            + (
                binding.model_copy(
                    update={
                        "requirement_id": "secondary_archive",
                        "capability_id": "acme.secondary_archive",
                    }
                ),
            ),
        }
    )
    entries = [
        _entry("acme.safe_archive", "pre_submit", deadline_ms=3_600_000),
        _entry("acme.secondary_archive", "pre_submit", deadline_ms=3_600_000),
        _entry("acme.quality_review", "post_submit"),
    ]
    with pytest.raises(ValueError, match="ART custody deadline"):
        await compile_external_checker_policies(proposal, _Registry(entries))


def _forge_binding(configuration, *, declared=True, phase="post_submit"):
    """A binding over a published schema that does or does not declare forge facts."""
    properties = {
        "repository": {"type": "string"},
        "forge": {"type": "string"},
        "forge_origin": {"type": "string"},
    }
    if declared:
        properties[FORGE_FACTS_VERSION_KEY] = {"const": "v1"}
    document = {"type": "object", "properties": properties}
    schema = ExternalCheckerSchema(
        schema_id="harnessy_work_proof_config",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    return LockedExternalCheckerBinding(
        requirement_id="harnessy.work_proof",
        stage=phase,
        registry=_entry("harnessy.work_proof", phase, configuration_schema=schema),
        configuration=configuration,
        configuration_sha256=external_checker_json_hash(configuration),
    )


_FORGE_SELECTION = {
    FORGE_FACTS_VERSION_KEY: "v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "Flow-Research/harnessy-v2",
    "base_branch": "dev",
}


def test_forge_facts_are_selected_only_by_an_exact_declared_post_capability():
    binding = _forge_binding(_FORGE_SELECTION)
    assert selected_forge_facts(binding.configuration, binding.stage) == ForgeFactsSelection(
        forge="github",
        forge_origin="https://github.com",
        repository="Flow-Research/harnessy-v2",
        base_branch="dev",
    )
    # A neutral path may hold subgroups and a self-hosted instance with a port.
    assert selected_forge_facts(
        {
            **_FORGE_SELECTION,
            "forge_origin": "https://git.example.org:8443",
            "repository": "group/subgroup/project",
        },
        "post_submit",
    ) == ForgeFactsSelection(
        forge="github",
        forge_origin="https://git.example.org:8443",
        repository="group/subgroup/project",
        base_branch="dev",
    )
    assert selected_forge_facts({"repository": "a/b"}, "post_submit") is None
    with pytest.raises(ValueError, match="schema does not declare forge facts"):
        _forge_binding(_FORGE_SELECTION, declared=False)


@pytest.mark.parametrize(
    "changes",
    [
        {FORGE_FACTS_VERSION_KEY: "v2"},
        {"forge": "gitlab"},
        {"forge": None},
        {"repository": "Flow-Research"},
        {"repository": "https://github.com/Flow-Research/harnessy-v2"},
        {"repository": "Flow-Research/.."},
        {"repository": "a/" + "b" * 254},
        {"forge_origin": None},
        {"forge_origin": "http://github.com"},
        {"forge_origin": "https://github.com/"},
        {"forge_origin": "https://github.com/Flow-Research"},
        {"base_branch": ""},
        {"base_branch": 7},
    ],
)
def test_invalid_forge_facts_selection_never_reads_facts(changes):
    with pytest.raises(ExternalCheckerPolicyError, match="forge facts selection"):
        selected_forge_facts({**_FORGE_SELECTION, **changes}, "post_submit")


def test_pre_submit_cannot_select_forge_facts():
    with pytest.raises(ExternalCheckerPolicyError, match="forge facts selection"):
        selected_forge_facts(_FORGE_SELECTION, "pre_submit")


def test_selected_post_budget_reserves_the_forge_facts_read():
    plain, selected = _forge_binding({}), _forge_binding(_FORGE_SELECTION)

    def budget(binding):
        body = {
            "schema_version": "external_post_submit_policy.v1",
            "entries": [binding.model_dump(mode="json")],
        }
        return selected_post_submit_execution_budget_ms(
            LockedExternalPostSubmitPolicy(
                entries=(binding,), policy_sha256=canonical_json_hash(body)
            )
        )

    assert budget(selected) - budget(plain) == SELECTED_POST_FORGE_FACTS_BUDGET_MS
