"""Closed-contract proof for the inert REV authorization integration surface."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.actors.service_identities import ServiceIdentity
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionAvailability, ActionId
from app.modules.authorization.prepared import PreparedAuthorizationHandle
from app.modules.authorization.runtime import PROJECT_MUTATION_RESOURCE_BY_ACTION
from app.modules.authorization.review_contracts import (
    EXTERNAL_REVIEW_AUTHORIZATION_HANDOFFS,
    EXISTING_REVIEW_SETUP_CONTRACTS,
    REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION,
    QueueSelectionMode,
    ReconciliationMode,
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
    RevisionPreparationDirection,
    RevisionPreparationOutcome,
    RevisionClosureCause,
)

SHA = "sha256:" + "a" * 64
NOW = datetime(2026, 8, 3, tzinfo=UTC)


def _queue_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_QUEUE_READ,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": uuid4(),
        "queue_entry_id": uuid4(),
        "queue_generation": 1,
        "task_id": uuid4(),
        "task_assignment_id": uuid4(),
        "submission_id": uuid4(),
        "checker_run_id": uuid4(),
        "reviewer_actor_profile_id": uuid4(),
        "contributor_actor_profile_id": uuid4(),
        "reviewer_grant_id": uuid4(),
        "review_policy_id": uuid4(),
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
        "project_id": uuid4(),
        "shard": "project:0",
        "trigger": "grant_revoked",
        "finding_ids_digest": SHA,
        "observed_at": NOW,
        "watermark": "42",
    }


def _decision_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_DECISION,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": uuid4(),
        "task_id": uuid4(),
        "task_assignment_id": uuid4(),
        "submission_id": uuid4(),
        "checker_run_id": uuid4(),
        "queue_entry_id": uuid4(),
        "review_lease_id": uuid4(),
        "reviewer_actor_profile_id": uuid4(),
        "packet_manifest_id": uuid4(),
        "packet_manifest_generation": 1,
        "packet_manifest_digest": SHA,
        "artifact_binding_id": uuid4(),
        "chain_digest": SHA,
        "review_operation_id": uuid4(),
        "decision_shape": "initial",
        "decision": ReviewDecisionValue.ACCEPT,
        "finding_count": 0,
        "blocking_finding_count": 0,
        "findings_resolutions_digest": SHA,
        "review_policy_id": uuid4(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "reviewer_contribution_policy_id": uuid4(),
        "reviewer_contribution_policy_generation": 1,
        "reviewer_contribution_policy_digest": SHA,
        "artifact_hash": SHA,
    }


def _obligation_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_REVISION_OBLIGATION_CLOSE,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": uuid4(),
        "task_id": uuid4(),
        "task_assignment_id": uuid4(),
        "source_task_assignment_id": uuid4(),
        "prior_submission_id": uuid4(),
        "needs_revision_review_id": uuid4(),
        "revision_episode_id": uuid4(),
        "preparation_head_id": uuid4(),
        "preparation_head_generation": 1,
        "preparation_head_digest": SHA,
        "revision_policy_id": uuid4(),
        "revision_policy_generation": 1,
        "revision_policy_digest": SHA,
        "revision_round": 3,
        "revision_limit": 3,
        "observed_at": NOW,
        "reached_cause": RevisionClosureCause.LIMIT_REACHED,
    }


def test_manifest_exactly_covers_registered_review_actions_and_stays_unavailable():
    expected = frozenset(action for action in ActionId if action.value.startswith("review."))

    assert frozenset(REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION) == expected
    assert all(
        ACTION_BY_ID[action].availability is ActionAvailability.PLANNED for action in expected
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
    forbidden_names = {
        "authorization_handle",
        "prepared_authorization",
        "bytes",
        "content",
        "provider_credentials",
        "scratch_path",
        "callback",
    }
    for spec in REVIEW_AUTHORIZATION_CONTRACT_BY_ACTION.values():
        for model in spec.resource_models:
            assert forbidden_names.isdisjoint(model.model_fields)
            assert all(
                field.annotation is not PreparedAuthorizationHandle
                for field in model.model_fields.values()
            )


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
        "project_id": uuid4(),
        "selection_mode": QueueSelectionMode.NONE,
        "reviewer_actor_profile_id": uuid4(),
        "reviewer_grant_id": uuid4(),
        "review_policy_id": uuid4(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "queue_state_digest": SHA,
    }
    result = ReviewQueueNoneContract.model_validate(values)
    assert "submission_id" not in type(result).model_fields
    with pytest.raises(ValidationError):
        ReviewQueueNoneContract.model_validate(values | {"submission_id": uuid4()})
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
            "execution_mode": ReconciliationMode.AUTHORITY_INVALIDATION,
        }
    )
    assert authority.execution_mode is ReconciliationMode.AUTHORITY_INVALIDATION

    general = ReviewGeneralReconcileContract.model_validate(
        values
        | {
            "service_identity": ServiceIdentity.REVIEW_RECONCILIATION,
            "execution_mode": ReconciliationMode.GENERAL,
            "reason": "scheduled bounded reconciliation",
        }
    )
    assert general.execution_mode is ReconciliationMode.GENERAL

    with pytest.raises(ValidationError):
        ReviewAuthorityInvalidationReconcileContract.model_validate(
            values
            | {
                "service_identity": ServiceIdentity.REVIEW_RECONCILIATION,
                "execution_mode": ReconciliationMode.AUTHORITY_INVALIDATION,
            }
        )
    with pytest.raises(ValidationError):
        ReviewGeneralReconcileContract.model_validate(
            values
            | {
                "service_identity": ServiceIdentity.REVIEW_RECONCILIATION,
                "execution_mode": ReconciliationMode.AUTHORITY_INVALIDATION,
                "reason": "wrong mode",
            }
        )


def test_lease_and_preference_statuses_are_closed():
    lease_values = {
        "action_id": ActionId.REVIEW_RELEASE,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": uuid4(),
        "queue_entry_id": uuid4(),
        "review_lease_id": uuid4(),
        "lease_generation": 1,
        "reviewer_actor_profile_id": uuid4(),
        "task_id": uuid4(),
        "submission_id": uuid4(),
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
        "project_id": uuid4(),
        "queue_entry_id": uuid4(),
        "preference_id": uuid4(),
        "preference_generation": 1,
        "preferred_reviewer_actor_profile_id": uuid4(),
        "source_review_id": uuid4(),
        "source_submission_id": uuid4(),
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
        "predecessor_review_id": uuid4(),
        "predecessor_submission_id": uuid4(),
        "revision_episode_id": uuid4(),
        "preparation_head_id": uuid4(),
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
            _decision_values() | {"predecessor_review_id": uuid4()}
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
        "guide_id": uuid4(),
        "guide_activation_sequence": 2,
        "review_policy_id": uuid4(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "revision_policy_id": uuid4(),
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


def test_lifecycle_activation_rejects_same_phase_and_stays_scalar_serializable():
    values = {
        "action_id": ActionId.REVIEW_LIFECYCLE_ACTIVATION_MANAGE,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "singleton_id": uuid4(),
        "operation_id": uuid4(),
        "expected_generation": 1,
        "current_phase": ReviewLifecyclePhase.SHADOW,
        "target_phase": ReviewLifecyclePhase.DRAINING,
        "adjacent_transition_confirmed": True,
        "reviewed_manifest_digest": SHA,
        "drain_observations_digest": SHA,
        "batch_limit": 100,
        "deadline": NOW,
        "reason": "reviewed activation transition",
    }
    contract = ReviewLifecycleActivationContract.model_validate(values)
    assert "PreparedAuthorizationHandle" not in contract.model_dump_json()
    with pytest.raises(ValidationError):
        ReviewLifecycleActivationContract.model_validate(
            values | {"target_phase": ReviewLifecyclePhase.SHADOW}
        )


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
