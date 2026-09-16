"""Real activated guide context shared by complete-context proofs."""

from contextlib import asynccontextmanager

from app.modules.projects.api import ProjectLockedPolicyContextRequest
from tests.authorization.guide_activation.pg_support import activate
from tests.projects.guide_activation.pg_support import activation_case


def frozen_request(receipt):
    target, upstream = receipt.command.target.proposal, receipt.command.target.upstream
    return ProjectLockedPolicyContextRequest(
        project_id=target.project_id,
        guide_version=target.guide_version,
        source_snapshot_id=target.source_snapshot_id,
        source_snapshot_hash=target.source_snapshot_hash,
        effective_policy_id=upstream.effective_policy_id,
        effective_policy_hash=upstream.effective_policy_hash,
        pre_submit_policy_id=upstream.pre_submit_policy_id,
        pre_submit_policy_bundle_hash=upstream.pre_submit_bundle_hash,
    )


@asynccontextmanager
async def activated_context(url):
    async with activation_case(url) as (factory, command, actor, grant, world, policy):
        receipt = await activate(factory, actor, command)
        yield factory, receipt, actor, grant, world, policy
