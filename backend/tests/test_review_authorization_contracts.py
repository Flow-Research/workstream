"""Closed-contract proof for the inert REV authorization integration surface."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import NoneType, UnionType
from typing import Literal, Union, get_args, get_origin
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from pydantic import AwareDatetime, ValidationError

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.runtime import PROJECT_MUTATION_RESOURCE_BY_ACTION
from app.modules.authorization.review_contracts import (
    EXTERNAL_REVIEW_AUTHORIZATION_HANDOFFS,
    EXISTING_REVIEW_SETUP_CONTRACTS,
    REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION,
    QueueSelectionMode,
    ReviewAuthorityInvalidationReconcileContract,
    ReviewAuthorizationResourceContract,
    ReviewContractExecution,
    ReviewDecisionContract,
    ReviewDecisionValue,
    ReviewGeneralReconcileContract,
    ReviewLifecycleActivationContract,
    ReviewLifecyclePhase,
    ReviewLeaseStatus,
    ReviewPreferenceStatus,
    ReviewQueueNoneContract,
    ReviewQueueReadContract,
    ReviewReleaseContract,
    ReviewDeclinePreferenceContract,
    ReviewRevisionContextRepairContract,
    ReviewRevisionDecisionContract,
    ReviewRevisionObligationCloseContract,
    ServiceExecutionMode,
    RevisionPreparationDirection,
    RevisionPreparationOutcome,
    RevisionClosureCause,
)

from tests.authorization.review_contract_fixtures import _decision_values

SHA = "sha256:" + "a" * 64
NOW = datetime(2026, 8, 3, tzinfo=UTC)


def _queue_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_QUEUE_READ,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "queue_entry_id": new_record_id(),
        "queue_generation": 1,
        "task_id": new_record_id(),
        "task_assignment_id": new_record_id(),
        "submission_id": new_record_id(),
        "checker_run_id": new_record_id(),
        "reviewer_actor_profile_id": new_record_id(),
        "contributor_actor_profile_id": new_record_id(),
        "reviewer_grant_id": new_record_id(),
        "review_policy_id": new_record_id(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "queue_state_digest": SHA,
        "no_self_review": True,
        "selection_mode": QueueSelectionMode.OFFER,
    }


def _reconcile_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_RECONCILE_RUN,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "shard": "project:0",
        "trigger": "grant_revoked",
        "finding_ids_digest": SHA,
        "observed_at": NOW,
        "watermark": "42",
    }


def _obligation_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_REVISION_OBLIGATION_CLOSE,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "task_id": new_record_id(),
        "task_assignment_id": new_record_id(),
        "source_task_assignment_id": new_record_id(),
        "prior_submission_id": new_record_id(),
        "needs_revision_review_id": new_record_id(),
        "revision_episode_id": new_record_id(),
        "preparation_head_id": new_record_id(),
        "preparation_head_generation": 1,
        "preparation_head_digest": SHA,
        "revision_policy_id": new_record_id(),
        "revision_policy_generation": 1,
        "revision_policy_digest": SHA,
        "revision_round": 3,
        "revision_limit": 3,
        "observed_at": NOW,
        "reached_cause": RevisionClosureCause.LIMIT_REACHED,
    }


def test_manifest_covers_review_actions_with_only_scoped_controller_available():
    expected = frozenset(action for action in ActionId if action.value.startswith("review."))

    assert frozenset(REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION) == expected
    assert all(
        ACTION_BY_ID[action].availability is ActionAvailability.PLANNED
        for action in expected - {ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE}
    )
    assert {
        action
        for action, spec in REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION.items()
        if spec.execution is ReviewContractExecution.UNSUPPORTED_FUTURE_INTENT
    } == {
        ActionId.REVIEW_FINDING_EVIDENCE_INGEST,
        ActionId.REVIEW_FINDING_RESPONSE_EVIDENCE_INGEST,
    }


def test_every_executable_manifest_model_has_one_exact_action_discriminator():
    for action, spec in REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION.items():
        if spec.execution is ReviewContractExecution.UNSUPPORTED_FUTURE_INTENT:
            assert spec.resource_models == ()
            continue
        assert spec.resource_models
        for model in spec.resource_models:
            assert get_args(model.model_fields["action_id"].annotation) == (action,)
            assert model.model_config["extra"] == "forbid"
            assert model.model_config["frozen"] is True
            assert model.model_config["strict"] is True

    assert set(get_args(ReviewAuthorizationResourceContract)) == {
        model
        for spec in REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION.values()
        for model in spec.resource_models
    }


def test_contract_models_exclude_handles_callbacks_bytes_and_unbounded_maps():
    for spec in REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION.values():
        for model in spec.resource_models:
            _assert_inert_contract_model(model)


def _assert_inert_contract_model(model):
    """Recursively require closed scalar models, enums and optional fields."""

    def assert_allowed(annotation, field_name):
        origin = get_origin(annotation)
        if origin is Literal:
            return
        if origin in (Union, UnionType):
            for member in get_args(annotation):
                assert_allowed(member, field_name)
            return
        from pydantic import BaseModel
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            assert annotation.model_config.get("extra") == "forbid"
            assert annotation.model_config.get("frozen") is True
            _assert_inert_contract_model(annotation)
            return
        assert annotation is not PreparedAuthorizationHandle, field_name
        assert annotation not in (bytes, bytearray), field_name
        assert annotation in (str, int, bool, datetime, AwareDatetime, UUID, NoneType) or (
            isinstance(annotation, type) and issubclass(annotation, Enum)
        ), field_name

    for name, field in model.model_fields.items():
        assert_allowed(field.annotation, name)


def test_external_handoffs_are_closed_references_not_review_contracts():
    assert dict(EXTERNAL_REVIEW_AUTHORIZATION_HANDOFFS) == {
        ActionId.ARTIFACT_REVIEW_PACKET_MATERIALIZE: "WS-XINT-002-07A",
        ActionId.ARTIFACT_REVIEW_EVIDENCE_BINDING_CREATE: "future REV-owned intent",
        ActionId.ARTIFACT_SUBMISSION_BUNDLE_PREPARE: "WS-XINT-002-05D",
        ActionId.SUBMISSION_CREATE: "WS-XINT-002-05D",
    }
    assert set(EXTERNAL_REVIEW_AUTHORIZATION_HANDOFFS).isdisjoint(
        REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION
    )


def test_already_active_policy_setup_reuses_existing_exact_runtime_contracts():
    assert set(EXISTING_REVIEW_SETUP_CONTRACTS) == {
        ActionId.PROJECT_REVIEW_POLICY_UPDATE,
        ActionId.PROJECT_REVISION_POLICY_UPDATE,
    }
    assert set(EXISTING_REVIEW_SETUP_CONTRACTS.values()) == {
        "ProjectReviewPolicyMutationResourceContext",
        "ProjectRevisionPolicyMutationResourceContext",
    }
    assert {
        action: PROJECT_MUTATION_RESOURCE_BY_ACTION[action].__name__
        for action in EXISTING_REVIEW_SETUP_CONTRACTS
    } == dict(EXISTING_REVIEW_SETUP_CONTRACTS)


def test_queue_contract_rejects_self_review_wrong_action_extra_and_inconsistent_lease():
    values = _queue_values()
    assert ReviewQueueReadContract.model_validate(values).model_dump(mode="json")

    with pytest.raises(ValidationError):
        ReviewQueueReadContract.model_validate(values | {"unexpected": "authority"})
    with pytest.raises(ValidationError):
        ReviewQueueReadContract.model_validate(values | {"action_id": ActionId.REVIEW_CLAIM})
    with pytest.raises(ValidationError):
        ReviewQueueReadContract.model_validate(
            values | {"contributor_actor_profile_id": values["reviewer_actor_profile_id"]}
        )
    with pytest.raises(ValidationError, match="no-self-review proof must be true"):
        ReviewQueueReadContract.model_validate(values | {"no_self_review": False})
    with pytest.raises(ValidationError):
        ReviewQueueReadContract.model_validate(
            values | {"selection_mode": QueueSelectionMode.ACTIVE_LEASE}
        )

    changed = ReviewQueueReadContract.model_validate(
        values | {"queue_state_digest": "sha256:" + "b" * 64}
    )
    assert changed != ReviewQueueReadContract.model_validate(values)


def test_queue_none_contract_is_minimal_and_rejects_lineage_disclosure():
    values = {
        "action_id": ActionId.REVIEW_QUEUE_READ,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "selection_mode": QueueSelectionMode.NONE,
        "reviewer_actor_profile_id": new_record_id(),
        "reviewer_grant_id": new_record_id(),
        "review_policy_id": new_record_id(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "queue_state_digest": SHA,
    }
    result = ReviewQueueNoneContract.model_validate(values)
    assert "submission_id" not in type(result).model_fields
    with pytest.raises(ValidationError):
        ReviewQueueNoneContract.model_validate(values | {"submission_id": new_record_id()})
    with pytest.raises(ValidationError):
        ReviewQueueReadContract.model_validate(
            _queue_values() | {"selection_mode": QueueSelectionMode.NONE}
        )


def test_reconciliation_identity_and_mode_cannot_be_swapped():
    values = _reconcile_values()
    authority = ReviewAuthorityInvalidationReconcileContract.model_validate(
        values
        | {
            "service_identity": ServiceIdentity.REVIEW_AUTHORITY_INVALIDATION_RECONCILIATION,
            "execution_mode": ServiceExecutionMode.AUTHORITY_INVALIDATION,
        }
    )
    assert authority.execution_mode is ServiceExecutionMode.AUTHORITY_INVALIDATION

    general = ReviewGeneralReconcileContract.model_validate(
        values
        | {
            "service_identity": ServiceIdentity.REVIEW_RECONCILIATION,
            "execution_mode": ServiceExecutionMode.GENERAL,
            "reason": "scheduled bounded reconciliation",
        }
    )
    assert general.execution_mode is ServiceExecutionMode.GENERAL

    with pytest.raises(ValidationError):
        ReviewAuthorityInvalidationReconcileContract.model_validate(
            values
            | {
                "service_identity": ServiceIdentity.REVIEW_RECONCILIATION,
                "execution_mode": ServiceExecutionMode.AUTHORITY_INVALIDATION,
            }
        )
    with pytest.raises(ValidationError):
        ReviewGeneralReconcileContract.model_validate(
            values
            | {
                "service_identity": ServiceIdentity.REVIEW_RECONCILIATION,
                "execution_mode": ServiceExecutionMode.AUTHORITY_INVALIDATION,
                "reason": "wrong mode",
            }
        )


def test_lease_and_preference_statuses_are_closed():
    lease_values = {
        "action_id": ActionId.REVIEW_RELEASE,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "queue_entry_id": new_record_id(),
        "review_lease_id": new_record_id(),
        "lease_generation": 1,
        "reviewer_actor_profile_id": new_record_id(),
        "task_id": new_record_id(),
        "submission_id": new_record_id(),
        "lease_status": ReviewLeaseStatus.ACTIVE,
        "expires_at": NOW,
        "lease_state_digest": SHA,
        "reason": "reviewer release",
    }
    assert (
        ReviewReleaseContract.model_validate(lease_values).lease_status is ReviewLeaseStatus.ACTIVE
    )
    with pytest.raises(ValidationError):
        ReviewReleaseContract.model_validate(lease_values | {"lease_status": "unknown"})

    preference_values = {
        "action_id": ActionId.REVIEW_DECLINE_PREFERENCE,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "queue_entry_id": new_record_id(),
        "preference_id": new_record_id(),
        "preference_generation": 1,
        "preferred_reviewer_actor_profile_id": new_record_id(),
        "source_review_id": new_record_id(),
        "source_submission_id": new_record_id(),
        "preference_status": ReviewPreferenceStatus.ACTIVE,
        "expires_at": NOW,
        "preference_state_digest": SHA,
        "reason": "reviewer decline",
    }
    assert (
        ReviewDeclinePreferenceContract.model_validate(preference_values).preference_status
        is ReviewPreferenceStatus.ACTIVE
    )
    with pytest.raises(ValidationError):
        ReviewDeclinePreferenceContract.model_validate(
            preference_values | {"preference_status": "unknown"}
        )


def test_decision_requires_consistent_counts_and_blocking_finding_for_revision():
    values = _decision_values()
    assert ReviewDecisionContract.model_validate(values).decision is ReviewDecisionValue.ACCEPT
    with pytest.raises(ValidationError):
        ReviewDecisionContract.model_validate(
            values | {"finding_count": 0, "blocking_finding_count": 1}
        )
    with pytest.raises(ValidationError):
        ReviewDecisionContract.model_validate(
            values | {"decision": ReviewDecisionValue.NEEDS_REVISION}
        )
    revised = ReviewDecisionContract.model_validate(
        values
        | {
            "decision": ReviewDecisionValue.NEEDS_REVISION,
            "finding_count": 1,
            "blocking_finding_count": 1,
        }
    )
    assert revised.blocking_finding_count == 1


def test_revised_submission_decision_requires_exact_predecessor_and_response_lineage():
    values = _decision_values() | {
        "decision_shape": "revision",
        "predecessor_review_id": new_record_id(),
        "predecessor_submission_id": new_record_id(),
        "revision_episode_id": new_record_id(),
        "preparation_head_id": new_record_id(),
        "preparation_head_generation": 2,
        "preparation_head_digest": SHA,
        "finding_response_count": 1,
        "finding_response_lineage_digest": SHA,
    }
    contract = ReviewRevisionDecisionContract.model_validate(values)
    assert contract.predecessor_submission_id != contract.submission_id
    for field in (
        "predecessor_submission_id",
        "revision_episode_id",
        "preparation_head_id",
        "finding_response_lineage_digest",
    ):
        with pytest.raises(ValidationError):
            ReviewRevisionDecisionContract.model_validate(
                {key: value for key, value in values.items() if key != field}
            )
    with pytest.raises(ValidationError):
        ReviewDecisionContract.model_validate(
            _decision_values() | {"predecessor_review_id": new_record_id()}
        )
    with pytest.raises(ValidationError):
        ReviewRevisionDecisionContract.model_validate(
            values | {"predecessor_submission_id": values["submission_id"]}
        )
    with pytest.raises(ValidationError):
        ReviewRevisionDecisionContract.model_validate(values | {"decision_shape": "initial"})


def test_obligation_close_requires_the_selected_frozen_boundary_to_be_reached():
    values = _obligation_values()
    assert ReviewRevisionObligationCloseContract.model_validate(values).revision_round == 3
    with pytest.raises(ValidationError):
        ReviewRevisionObligationCloseContract.model_validate(values | {"revision_round": 2})
    with pytest.raises(ValidationError):
        ReviewRevisionObligationCloseContract.model_validate(
            values
            | {
                "reached_cause": RevisionClosureCause.DEADLINE_EXPIRED,
                "revision_deadline": None,
            }
        )
    expired = ReviewRevisionObligationCloseContract.model_validate(
        values
        | {
            "reached_cause": RevisionClosureCause.DEADLINE_EXPIRED,
            "revision_deadline": NOW,
        }
    )
    assert expired.reached_cause is RevisionClosureCause.DEADLINE_EXPIRED


def test_revision_repair_uses_canonical_outcome_direction_and_repairability():
    values = {
        key: value
        for key, value in _obligation_values().items()
        if key
        not in {
            "action_id",
            "revision_policy_id",
            "revision_policy_generation",
            "revision_policy_digest",
            "revision_round",
            "revision_limit",
            "observed_at",
            "reached_cause",
        }
    } | {
        "action_id": ActionId.REVIEW_REVISION_CONTEXT_REPAIR,
        "preparation_head_outcome": RevisionPreparationOutcome.BLOCKED,
        "preparation_head_repairable": True,
        "guide_id": new_record_id(),
        "guide_activation_sequence": 2,
        "review_policy_id": new_record_id(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "revision_policy_id": new_record_id(),
        "revision_policy_generation": 1,
        "revision_policy_digest": SHA,
        "reason": "repair blocked current context",
    }
    assert (
        ReviewRevisionContextRepairContract.model_validate(values).preparation_head_direction
        is None
    )
    with pytest.raises(ValidationError):
        ReviewRevisionContextRepairContract.model_validate(
            values | {"preparation_head_outcome": "unknown"}
        )
    with pytest.raises(ValidationError):
        ReviewRevisionContextRepairContract.model_validate(
            values | {"preparation_head_direction": RevisionPreparationDirection.FORWARD}
        )
    rebased = ReviewRevisionContextRepairContract.model_validate(
        values
        | {
            "preparation_head_outcome": RevisionPreparationOutcome.REBASED,
            "preparation_head_direction": RevisionPreparationDirection.BACKWARD,
        }
    )
    assert rebased.preparation_head_direction is RevisionPreparationDirection.BACKWARD


def test_lifecycle_activation_binds_canonical_command_and_observed_facts():
    from app.modules.reviews.api.lifecycle import (
        JointLifecyclePhase, LifecycleTransitionCommand, LifecycleTransitionFacts,
    )
    values = dict(
        operation_id=new_record_id(), singleton_id=new_record_id(),
        actor_profile_id=new_record_id(), identity_link_id=new_record_id(),
        expected_generation=0, current_phase=JointLifecyclePhase.DISABLED,
        target_phase=JointLifecyclePhase.SHADOW, reviewed_manifest_digest=SHA,
        deadline=NOW, reason="reviewed transition",
    )
    command = LifecycleTransitionCommand(**values)
    facts = LifecycleTransitionFacts(command=command, observations_digest=SHA)
    contract = ReviewLifecycleActivationContract(resource_id=command.singleton_id, facts=facts)
    assert ReviewLifecycleActivationContract.model_validate_json(contract.model_dump_json()) == contract
    with pytest.raises(ValidationError):
        ReviewLifecycleActivationContract(resource_id=new_record_id(), facts=facts)
    for changes in (
        {"expected_generation": True}, {"expected_generation": -1},
        {"expected_generation": 2**63 - 1},
        {"current_phase": JointLifecyclePhase.LIVE},
        {"target_phase": JointLifecyclePhase.DISABLED},
        {"adjacent_transition_confirmed": True},
    ):
        with pytest.raises(ValidationError):
            LifecycleTransitionCommand(**(values | changes))


def test_contract_module_has_no_rev_import_and_workers_carry_no_prepared_handle():
    app_root = Path(__file__).parents[1] / "app"
    contract_source = (app_root / "modules" / "authorization" / "review_contracts.py").read_text(
        encoding="utf-8"
    )
    assert "app.modules.review" not in contract_source
    assert "PreparedAuthorizationHandle" not in contract_source

    worker_sources = [
        path.read_text(encoding="utf-8")
        for path in app_root.rglob("*.py")
        if "worker" in path.name or "tasks" in path.parts
    ]
    assert worker_sources
    assert all("PreparedAuthorizationHandle" not in source for source in worker_sources)


@pytest.mark.parametrize("decision,new_blockers,inherited,valid", (
    (ReviewDecisionValue.NEEDS_REVISION, 0, 1, True),
    (ReviewDecisionValue.NEEDS_REVISION, 0, 0, False),
    (ReviewDecisionValue.ACCEPT, 0, 1, False),
    (ReviewDecisionValue.ACCEPT, 1, 0, False),
    (ReviewDecisionValue.ACCEPT, 0, 0, True),
    (ReviewDecisionValue.NEEDS_REVISION, 100, 1, False),
    (ReviewDecisionValue.NEEDS_REVISION, 99, 1, True),
))
def test_revision_decision_counts_inherited_open_blockers(decision, new_blockers, inherited, valid):
    values = _decision_values() | {
        "decision_shape": "revision", "submission_version": 2,
        "predecessor_review_id": new_record_id(), "predecessor_submission_id": new_record_id(),
        "revision_episode_id": new_record_id(), "preparation_head_id": new_record_id(),
        "preparation_head_generation": 1, "preparation_head_digest": SHA,
        "finding_response_count": inherited, "finding_response_lineage_digest": SHA,
        "decision": decision, "finding_count": new_blockers, "blocking_finding_count": new_blockers,
        "inherited_unresolved_blocking_count": inherited,
    }
    if valid:
        assert ReviewRevisionDecisionContract(**values).decision is decision
    else:
        with pytest.raises(ValidationError, match="blocking finding"):
            ReviewRevisionDecisionContract(**values)


def test_initial_decision_cannot_claim_inherited_blockers():
    values = _decision_values() | {"decision": ReviewDecisionValue.NEEDS_REVISION, "inherited_unresolved_blocking_count": 1}
    with pytest.raises(ValidationError, match="initial decision has inherited blockers"):
        ReviewDecisionContract(**values)
