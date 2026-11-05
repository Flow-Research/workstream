"""Real fixed-service execution fixtures and explicit forbidden phase participants."""

import pytest
from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorProfile, ActorIdentityLink


class ControlledSelectedExecution:
    """Return one request-bound selected result without replacing owner logic."""

    def __init__(self, *, verdict="passed", findings=None):
        self.verdict = verdict
        self.findings = findings
        self.requests = []

    async def execute(self, request, grant):
        from app.interfaces.external_checker_execution import (
            ExternalCheckerExecutionResponse,
            ExternalCheckerIsolationReceipt,
            ExternalCheckerMaterialGrant,
        )
        from app.modules.checkers.api.external import (
            make_external_checker_execution_result,
        )

        assert type(grant) is ExternalCheckerMaterialGrant
        self.requests.append(request)
        findings = self.findings if self.findings is not None else (
            () if self.verdict == "passed" else ({
            "check_id": "post_evidence",
            "code": "post_evidence_failed",
            "level": "error",
            "message": "Post evidence failed.",
        },))
        result = make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase=request.identity.phase,
            outcome="completed",
            verdict=self.verdict,
            findings=findings,
            infrastructure_failure_code=None,
        )
        sha = "sha256:" + "a" * 64
        return ExternalCheckerExecutionResponse(
            result=result,
            isolation=ExternalCheckerIsolationReceipt(
                repository="registry.example/workstream/checker",
                platform_manifest_digest=request.registry.image_digest,
                platform_manifest_media_type=(
                    "application/vnd.oci.image.manifest.v1+json"
                ),
                platform_manifest_byte_count=1024,
                operating_system="linux",
                architecture="amd64",
                config_image_id=sha,
                runtime="runsc",
                isolation_mode="gvisor",
                sandbox_uid=65532,
                sandbox_gid=65532,
            ),
        )


def selected_request(*, project_id=None):
    """Supply a closed empty selected policy for pure contract boundary tests."""
    from app.core.hashing import canonical_json_hash
    from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
    from app.modules.checkers.api.selected_post_submit import (
        SelectedPostSubmitLockedContext, make_selected_post_submit_request,
    )

    sha = "sha256:" + "a" * 64
    policy = LockedExternalPostSubmitPolicy(
        entries=(), policy_sha256=canonical_json_hash({
            "schema_version": "external_post_submit_policy.v1", "entries": [],
        }),
    )
    context = {
        name: (new_record_id() if name.endswith("_id") else
               1 if name.endswith("generation") else
               "v1" if "version" in name else sha)
        for name in SelectedPostSubmitLockedContext.model_fields
    }
    context["post_policy_hash"] = policy.policy_sha256
    return make_selected_post_submit_request(
        project_id=project_id or new_record_id(),
        expected_context=SelectedPostSubmitLockedContext(**context), policy=policy,
        evaluation_request_id=new_record_id(), evaluation_generation=1,
        task_id=new_record_id(), assignment_id=new_record_id(),
        submission_id=new_record_id(), submission_version=1,
        content_id=new_record_id(), binding_id=new_record_id(),
        content_sha256=sha, byte_count=42,
    )


def selected_result(source, **changes):
    """Supply closed empty-policy evidence for owner and material boundary tests."""
    from app.modules.checkers.api.selected_post_submit import (
        SelectedPostSubmissionEvaluationRequest,
        SelectedPostSubmitExecutionFacts,
        make_selected_post_submit_result,
    )

    source = SelectedPostSubmissionEvaluationRequest.model_validate(source)
    assert source.policy.entries == (), "external members require actual image execution"
    fields = dict(
        request_id=source.evaluation_request_id,
        request_digest=source.request_sha256,
        attempt_id=new_record_id(),
        evaluation_generation=source.evaluation_generation,
        result_id=new_record_id(),
        outcome="completed",
        execution=SelectedPostSubmitExecutionFacts(source.policy.policy_sha256, 0, ()),
        infrastructure_failure_code=None,
    )
    fields.update(changes)
    return make_selected_post_submit_result(**fields)


class ForbiddenPostSubmission:
    async def evaluate_post_submission(self, request):
        pytest.fail("pre-submit-only test entered post-submit execution")


def forbidden_post_submission():
    return ForbiddenPostSubmission()


async def provision_post_submit_service(factory, identity=ServiceIdentity.CHECKER_POST_SUBMIT):
    """Create fixture principal once without resetting an existing lifecycle decision."""
    async with factory() as session, session.begin():
        existing = await session.scalar(
            select(ActorProfile).where(
                ActorProfile.service_identity == identity.value,
            )
        )
        if existing is not None:
            return existing.id
        actor_id, link_id = str(new_record_id()), str(new_record_id())
        session.add(
            ActorProfile(
                id=actor_id,
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=identity.value,
                created_by="checker-test",
            )
        )
        session.add(
            ActorIdentityLink(
                id=link_id,
                actor_profile_id=actor_id,
                issuer="flow-test",
                subject=actor_id,
                subject_kind="service",
                status="active",
                linked_by="checker-test",
            )
        )
        return actor_id


def live_executor(h, *, outbox=None, selected_execution=None, forge_facts=None):
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.outbox import outbox_append
    from app.adapters.projects import project_locked_policy_context_port
    from app.modules.checkers.execution import PostSubmissionExecutor

    return PostSubmissionExecutor(
        sessions=h.factory,
        materialization=h.service,
        execute_authority=post_submit_execution_authority,
        finalize_authority=post_submit_execution_authority,
        selected_execution=selected_execution or ControlledSelectedExecution(),
        forge_facts=forge_facts,
        outbox=outbox if outbox is not None else outbox_append,
        review_modes=project_locked_policy_context_port,
    )


async def reserve(h, request=None):
    from app.adapters.checkers import evaluation_coordinator

    async with h.factory() as session, session.begin():
        return await evaluation_coordinator(session).reserve_current_evaluation(
            request if request is not None else h.request,
        )


async def material_execution(h):
    """Obtain one real committed execution lease for direct ART boundary tests."""
    from app.modules.checkers.api.execution import ExecuteFacts

    await reserve(h)
    lease, replay = await live_executor(h)._claim(h.request)
    assert replay is None
    return ExecuteFacts(request=h.request, lease=lease)


async def service_link_state(factory, identity, *, active):
    """Change real persisted service lifecycle in an independent transaction."""
    from sqlalchemy import text

    async with factory() as session, session.begin():
        if active:
            await session.execute(
                text(
                    "update actor_identity_links set status='active', revoked_by=null, revoked_at=null, "
                    "revoked_reason=null, reactivated_by='test', reactivated_at=clock_timestamp(), "
                    "reactivation_reason='test' where actor_profile_id="
                    "(select id from actor_profiles where service_identity=:identity)"
                ),
                {"identity": identity.value},
            )
        else:
            await session.execute(
                text(
                    "update actor_identity_links set status='revoked', revoked_by='test', "
                    "revoked_at=clock_timestamp(), revoked_reason='test' where actor_profile_id="
                    "(select id from actor_profiles where service_identity=:identity)"
                ),
                {"identity": identity.value},
            )
