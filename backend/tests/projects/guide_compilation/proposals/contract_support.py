"""Shared proposal values without importing collected test modules."""

from uuid import uuid4

from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.authorization.api.guide_proposal_review import (
    GuideProposalAuthorizationFacts,
    GuideProposalAuthorizationLocator,
    GuideProposalAuthorityReceipt,
)
from app.modules.projects.api.compilation_identity import CompilationComponentHashes
from app.modules.projects.api.guide_proposals import GuideProposalTarget

HASH = "sha256:" + "a" * 64


def target_values():
    return dict(
        project_id=uuid4(),
        guide_id=uuid4(),
        compilation_id=uuid4(),
        guide_version="1",
        source_snapshot_id=uuid4(),
        source_snapshot_hash=HASH,
        setup_run_id=uuid4(),
        setup_generation=1,
        finalization_id=uuid4(),
        finalization_facts_digest=HASH,
        result_hash=HASH,
        component_hashes={name: HASH for name in CompilationComponentHashes.model_fields},
        pre_catalogue_id="pre",
        pre_catalogue_version="1",
        pre_catalogue_schema_version="1",
        pre_catalogue_manifest_hash=HASH,
        post_catalogue_id="post",
        post_catalogue_version="1",
        post_catalogue_schema_version="1",
        post_catalogue_manifest_hash=HASH,
        artifact_policy_id=uuid4(),
        artifact_policy_hash=HASH,
        artifact_projection_operation_id=uuid4(),
        artifact_projection_output_digest=HASH,
    )


def authority_case():
    actor = ActorIdentityFacts(uuid4(), uuid4(), ActorKind.HUMAN)
    target = GuideProposalTarget(**target_values())
    locator = GuideProposalAuthorizationLocator(
        project_id=target.project_id,
        guide_id=target.guide_id,
        compilation_id=target.compilation_id,
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        action_id="project.submission_artifact_policy.approve",
        operation_id=uuid4(),
        request_id=uuid4(),
    )
    facts = GuideProposalAuthorizationFacts(
        locator=locator,
        finalization_id=target.finalization_id,
        artifact_policy_id=target.artifact_policy_id,
        setup_run_id=target.setup_run_id,
        setup_generation=target.setup_generation,
        target_digest=target.digest,
        request_digest="sha256:" + "a" * 64,
        output_digest="sha256:" + "b" * 64,
        current_approval_operation_id=None,
        current_approval_output_digest=None,
    )
    receipt = GuideProposalAuthorityReceipt(
        actor_profile_id=actor.actor_profile_id,
        identity_link_id=actor.identity_link_id,
        admin_role_grant_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        action_id=locator.action_id,
        permission_id="project.effective_policy.manage",
        scope_project_id=target.project_id,
        resource_context_digest=facts.digest,
    )
    return actor, target, facts, receipt
