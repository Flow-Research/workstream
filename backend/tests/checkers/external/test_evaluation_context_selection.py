"""Historical material is an explicit approved POST image capability."""

import pytest
from pydantic import ValidationError

from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import (
    EVALUATION_CONTEXT_ROLES_KEY as ROLES,
    EVALUATION_CONTEXT_VERSION_KEY as VERSION,
    ExternalCheckerPolicyError,
    LockedExternalCheckerBinding,
    selected_evaluation_context_roles,
)
from tests.checkers.external.test_policy import _entry


def _binding(configuration, *, declared=True):
    """Publish the declared immutable schema instead of injecting runtime properties."""
    document = {"type": "object"}
    if declared:
        document |= {
            "properties": {
                VERSION: {"const": "v1"},
                ROLES: {"type": "array", "items": {"type": "string"}},
            },
            "required": [VERSION, ROLES],
            "additionalProperties": False,
        }
    schema = ExternalCheckerSchema(
        schema_id="revision_context_config",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    return LockedExternalCheckerBinding(
        requirement_id="revision.objective",
        stage="post_submit",
        registry=_entry("project.revision", "post_submit", configuration_schema=schema),
        configuration=configuration,
        configuration_sha256=external_checker_json_hash(configuration),
    )


@pytest.mark.parametrize(
    "roles",
    [
        [],
        ["predecessor_findings"],
        ["predecessor_submission_archive"],
        ["predecessor_findings", "predecessor_submission_archive"],
    ],
)
def test_explicit_registry_and_approved_configuration_select_only_requested_roles(roles):
    binding = _binding({VERSION: "v1", ROLES: roles})
    assert selected_evaluation_context_roles(binding.configuration, binding.stage) == tuple(roles)


def test_absent_feature_stays_current_only_and_permissive_schema_cannot_invent_it():
    assert selected_evaluation_context_roles({}, "pre_submit") is None
    assert selected_evaluation_context_roles({}, "post_submit") is None
    with pytest.raises(ValidationError, match="schema does not declare"):
        _binding({VERSION: "v1", ROLES: []}, declared=False)


@pytest.mark.parametrize(
    "configuration",
    [
        {VERSION: "v1"},
        {ROLES: []},
        {VERSION: "v1", ROLES: [], "workstream_evaluation_context_extra": True},
        {VERSION: "v2", ROLES: []},
        {VERSION: "v1", ROLES: None},
        {VERSION: "v1", ROLES: ["other_contributor"]},
        {VERSION: "v1", ROLES: ["predecessor_findings", "predecessor_findings"]},
        {VERSION: "v1", ROLES: ["predecessor_submission_archive", "predecessor_findings"]},
        {VERSION: "v1", ROLES: [False]},
    ],
)
def test_invalid_selection_never_grants_context(configuration):
    with pytest.raises(ExternalCheckerPolicyError):
        selected_evaluation_context_roles(configuration, "post_submit")


def test_pre_submit_cannot_request_post_submission_context():
    with pytest.raises(ExternalCheckerPolicyError):
        selected_evaluation_context_roles({VERSION: "v1", ROLES: []}, "pre_submit")


@pytest.mark.parametrize("revision", [False, True])
async def test_selected_context_receipt_roundtrips_and_rejects_substituted_material(revision):
    """The real processor retains exact input hashes and only approved role facts."""
    from dataclasses import replace

    from app.core.hashing import canonical_json_hash
    from app.core.identifiers import new_record_id
    from app.modules.checkers.api.evaluation_context import PostSubmitEvaluationContext
    from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
    from app.modules.checkers.api.selected_post_submit import make_selected_post_submit_result
    from app.modules.checkers.api.evaluation_contract import validate_stored_execution_result
    from app.modules.checkers.selected_post_submit_execution import SelectedPostSubmitProcessor
    from tests.checkers.external.support import SHA, execution_identity, execution_material
    from tests.checkers.external.test_selected_post_submit import _policy, _MaterialView, _Execution, _request

    configured = _binding({VERSION: "v1", ROLES: ["predecessor_submission_archive"]})
    # Reuse the native POST input schema and a newly digest-bound registry spec.
    from app.modules.checkers.api.external import ExternalCheckerRegistryEntry, ExternalCheckerRegistrySpec
    original = _policy().entries[0].registry
    values = original.model_dump()
    values["configuration_schema"] = configured.registry.configuration_schema
    spec = ExternalCheckerRegistrySpec(**{key: values[key] for key in ExternalCheckerRegistrySpec.model_fields})
    values["entry_digest"] = spec.spec_digest
    binding = LockedExternalCheckerBinding(
        requirement_id=configured.requirement_id, stage="post_submit",
        registry=ExternalCheckerRegistryEntry(**values),
        configuration=configured.configuration,
        configuration_sha256=configured.configuration_sha256,
    )
    policy = LockedExternalPostSubmitPolicy(
        entries=(binding,), policy_sha256=canonical_json_hash({
            "schema_version": "external_post_submit_policy.v1", "entries": [binding.model_dump(mode="json")],
        }),
    )
    identity = execution_identity("post_submit")
    selected = _request(identity, policy)
    material = execution_material(identity).model_copy(update={
        "content_id": selected.content_id, "binding_id": selected.binding_id, "byte_count": selected.byte_count,
    })
    prior = material.model_copy(update={
        "role": "predecessor_submission_archive", "submission_id": new_record_id(),
        "submission_version": identity.submission_version - 1,
    })
    context = PostSubmitEvaluationContext.model_validate({
        "kind": "checker_remediation" if revision else "initial",
        "source": {
            "preparation_id": new_record_id(), "preparation_sha256": SHA,
            "routing_manifest_id": new_record_id(), "revision_round": 1,
            "evaluation": {
                "project_id": identity.project_id, "task_id": identity.task_id,
                "submission_id": prior.submission_id, "submission_version": prior.submission_version,
                "checker_run_id": new_record_id(), "evaluation_request_id": new_record_id(),
                "evaluation_request_digest": SHA, "evaluation_generation": 1,
                "result_id": new_record_id(), "result_digest": SHA,
                "completion_event_id": new_record_id(), "routing_recommendation": "needs_revision",
            },
        } if revision else None,
        "predecessor": {name: getattr(prior, name) for name in (
            "submission_id", "submission_version", "content_sha256", "byte_count", "semantic_manifest_sha256",
        )} if revision else None,
        "feedback": None,
    })
    materials = (material, prior) if revision else (material,)

    class ContextView(_MaterialView):
        def evaluation_material(self, approved):
            assert approved == binding
            return context, materials

    view, execution = ContextView(material), _Execution()
    facts = await SelectedPostSubmitProcessor(policy=policy, identity=identity, execution=execution).evaluate(selected, view)
    member = facts.external_members[0]
    wire = execution.requests[0]
    assert wire.materials == materials
    assert wire.input["evaluation_context"] == context.model_dump(mode="json")
    assert member.input_receipt.input_sha256 == wire.input_sha256
    assert member.input_receipt.evaluation_context_sha256 == canonical_json_hash(context.model_dump(mode="json"))
    retained = make_selected_post_submit_result(
        request_id=selected.evaluation_request_id, request_digest=selected.request_sha256,
        attempt_id=identity.attempt_id, result_id=identity.result_id,
        evaluation_generation=selected.evaluation_generation, outcome="completed",
        execution=facts, infrastructure_failure_code=None,
    )
    retained.validate_request(selected)
    restored = validate_stored_execution_result(retained.model_dump_json())
    assert restored == retained
    from types import SimpleNamespace
    from app.modules.artifacts.post_submit_materialization import _MaterialView as VerifiedView
    from app.modules.checkers.api.materialization import PostSubmissionMaterializationFailure

    # This pure owner validation needs detached verified facts only, not storage.
    owner_view = object.__new__(VerifiedView)
    owner_view._closed = False
    owner_view._execution = SimpleNamespace(request=selected)
    owner_view._materialization = SimpleNamespace(evaluation_context=context)
    owner_view._materials = materials
    owner_view.validate_evaluation(retained)
    for receipt in (
        replace(member.input_receipt, evaluation_context_sha256="sha256:" + "f" * 64),
        replace(member.input_receipt, materials=tuple(
            item.model_copy(update={"replica_id": new_record_id()}) for item in materials
        )),
    ):
        substituted = retained.model_copy(update={"execution": replace(
            facts, external_members=(replace(member, input_receipt=receipt),),
        )})
        with pytest.raises(PostSubmissionMaterializationFailure, match="input_receipt_mismatch"):
            owner_view.validate_evaluation(substituted)
    wrong = replace(member.input_receipt, materials=(material.model_copy(update={"content_id": new_record_id()}), *materials[1:]))
    changed = retained.model_copy(update={"execution": replace(facts, external_members=(replace(member, input_receipt=wrong),))})
    with pytest.raises(ValueError):
        changed.validate_request(selected)
