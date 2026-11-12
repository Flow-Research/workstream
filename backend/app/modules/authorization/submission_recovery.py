"""Current Operator decisions and exact retained causes for finalization recovery."""

from sqlalchemy import text

from app.modules.artifacts.api.submission_recovery import (
    SubmissionRecoveryAuthority, SubmissionRecoveryCommand, SubmissionRecoveryPayload,
    SubmissionRecoverySource, SubmissionRecoveryUnavailable,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.domain.submission_recovery import SubmissionRecoveryResourceContext
from app.modules.authorization.runtime import (
    AuthorizationDenied, HumanAuthorizationContext, authorization_resource_digest,
)


class SubmissionRecoveryAuthorization:
    def __init__(self, session, context, kernel):
        self._session, self._context, self._kernel = session, context, kernel

    @staticmethod
    def _resource(command, source, link_id):
        return SubmissionRecoveryResourceContext(
            resource_id=source.operation_id, scope_project_id=source.project_id,
            identity_link_id=link_id, command=command, source=source,
        )

    async def authorize(self, command, source):
        command = SubmissionRecoveryCommand.model_validate(command)
        source = SubmissionRecoverySource.model_validate(source)
        context = self._context
        if (not isinstance(context, HumanAuthorizationContext)
                or context.actor_profile_id != command.actor_profile_id
                or context.request_id != command.request_id
                or context.correlation_id != command.request_id):
            raise SubmissionRecoveryUnavailable("submission_recovery_authority_unavailable")
        resource = self._resource(command, source, context.identity_link_id)
        try:
            decision = await self._kernel.require(ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR, resource)
        except AuthorizationDenied as exc:
            raise SubmissionRecoveryUnavailable("submission_recovery_authority_unavailable") from exc
        digest = authorization_resource_digest(resource)
        if decision.resource_context_digest != digest:
            raise SubmissionRecoveryUnavailable("submission_recovery_authority_unavailable")
        return SubmissionRecoveryAuthority(decision_id=decision.decision_id,
            identity_link_id=context.identity_link_id, resource_digest=digest)

    async def validate_cause(self, payload):
        payload = SubmissionRecoveryPayload.model_validate(payload)
        command, source, authority = payload.command, payload.source, payload.authority
        digest = authorization_resource_digest(self._resource(command, source, authority.identity_link_id))
        event = (await self._session.execute(text(
            "SELECT event_type, actor_id, action_id, permission_id, project_id, resource_type, "
            "resource_id, request_id, correlation_id, denial_code, after_facts "
            "FROM public.audit_events WHERE id=:decision_id"
        ), {"decision_id": authority.decision_id})).mappings().one_or_none()
        if not (event is not None and authority.resource_digest == digest
                and event["event_type"] == "SensitiveAuthorizationAllowed"
                and event["actor_id"] == str(command.actor_profile_id)
                and event["action_id"] == ActionId.OPERATIONS_SUBMISSION_GATE_REPAIR.value
                and event["permission_id"] == PermissionId.OPERATIONS_SUBMISSION_GATE_REPAIR.value
                and str(event["project_id"]) == str(source.project_id)
                and event["resource_type"] == "submission_operation"
                and event["resource_id"] == str(source.operation_id)
                and str(event["request_id"]) == str(command.request_id)
                and str(event["correlation_id"]) == str(command.request_id)
                and event["denial_code"] is None
                and event["after_facts"] == {"allowed": True, "resource_context_digest": digest}):
            raise SubmissionRecoveryUnavailable("submission_recovery_cause_unavailable")

    async def restage_denial(self, error):
        if isinstance(error.__cause__, AuthorizationDenied):
            await self._kernel.restage_denial(error.__cause__.decision)
            return True
        return False
