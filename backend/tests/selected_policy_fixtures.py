"""Approved selected checker policy facts for current ART and TASK journeys."""

import json
from types import SimpleNamespace

from sqlalchemy import select


async def approved_selected_policy_fixture(
    factory,
    namespace,
    *,
    guide_version,
    contribution_awards=(),
    human_review_required=True,
    max_revision_rounds=2,
    pre_submit_registry_spec=None,
    post_submit_registry_spec=None,
    post_submit_binding_setup=None,
    post_submit_bindings_setup=None,
    post_submit_specification=None,
):
    """Build an activated guide backed only by immutable external policy custody."""
    from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
    from app.modules.projects.models import ProjectGuide, PostSubmitCheckerPolicy
    from tests.projects.unified_policy_fixtures import create_standalone_unified_policy

    values, effective, pre = await create_standalone_unified_policy(
        factory,
        namespace,
        guide_version=guide_version,
        contribution_awards=contribution_awards,
        human_review_required=human_review_required,
        max_revision_rounds=max_revision_rounds,
        artifact_proposal=SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes=1_000_000,
            maximum_package_size_bytes=5_000_000,
            required_artifacts=("task.toml",),
            required_evidence=("results",),
            attestation_terms=("rights_confirmed",),
        ),
        pre_submit_registry_spec=pre_submit_registry_spec,
        post_submit_registry_spec=post_submit_registry_spec,
        post_submit_binding_setup=post_submit_binding_setup,
        post_submit_bindings_setup=post_submit_bindings_setup,
        post_submit_specification=post_submit_specification,
    )
    async with factory() as session:
        guide = await session.get(ProjectGuide, str(values["guide"]))
        post = await session.scalar(
            select(PostSubmitCheckerPolicy).where(
                PostSubmitCheckerPolicy.effective_policy_id == effective["id"]
            )
        )
        assert post is not None
        assert pre.compiled_bundle.get("schema_version") == "external_pre_submit_policy.v1"
        assert post.policy_body.get("schema_version") == "external_post_submit_policy.v1"
        owner = SimpleNamespace(lineage=SimpleNamespace(project_id=values["project"]))
        return owner, {
            "post_policy": post.id,
            "post_policy_hash": post.policy_hash,
            "post_policy_body": json.dumps(post.policy_body),
            "submission_policy": effective["submission_artifact_policy_id"],
            "review_policy": guide.selected_review_policy_id,
            "review_policy_hash": guide.selected_review_policy_hash,
            "revision_policy": guide.selected_revision_policy_id,
            "revision_policy_hash": guide.selected_revision_policy_hash,
            "guide_version": guide_version,
            "attestation_terms": effective["effective_policy"]["attestation_terms"],
            "evidence_path": "evidence/"
            + effective["effective_policy"]["required_evidence"][0]["key"],
        }
