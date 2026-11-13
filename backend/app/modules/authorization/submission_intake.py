"""AUTH adapter for source reservation and current own-operation read authority."""
from dataclasses import asdict
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.authorization.api.submission_intake import (
    IntakeAuthorityDenied, IntakeOperationReadFacts, IntakeReservationAuthorityFacts, IntakeReservationPreflightFacts,
    IntakeAcceptanceAuthorityFacts,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.contributor_reads import ContributorWorkReadResourceContext
from app.modules.authorization.domain.submission_intake import (
    IntakeReservationResourceContext, IntakeReservationPreflightResourceContext, IntakeAcceptanceResourceContext,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationContext, AuthorizationDenied, HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput, PreparedAuthorizationUnsupported,
    PreparedAuthorityScope, PreparedAuthorityScopeKind,
)


class SubmissionIntakeAuthorization:
    """Reuse exact prepared handles and the current contributor read evaluator."""
    def __init__(self, session: AsyncSession, context: AuthorizationContext) -> None:
        self._session, self._context = session, context
        self._repository = AdminAuthorizationRepository(session)
        self._kernel = AuthorizationService(session, context, admin_repository=self._repository)
        self._prepared = PreparedAuthorizationService(session, context, self._kernel, self._repository)

    async def lock_actor(self, actor_id: UUID, identity_link_id: UUID) -> None:
        """Take actor/link locks after TASK and before PROJECT and grant locks."""
        context = self._context
        if (not self._session.in_transaction() or self._session.in_nested_transaction()
                or not isinstance(context, HumanAuthorizationContext)
                or (actor_id, identity_link_id) != (context.actor_profile_id, context.identity_link_id)):
            raise IntakeAuthorityDenied("submission intake is unavailable")
        locked = await self._repository.lock_request_actor(identity_link_id, actor_id)
        if locked is None:
            raise IntakeAuthorityDenied("submission intake is unavailable")
        link, profile = locked
        if (link.id != str(identity_link_id) or link.actor_profile_id != str(actor_id)
                or profile.id != str(actor_id) or profile.actor_kind != "human"
                or link.status != "active" or profile.status != "active"):
            raise IntakeAuthorityDenied("submission intake is unavailable")

    def _resource(self, facts: IntakeReservationAuthorityFacts) -> IntakeReservationResourceContext:
        if (type(facts) is not IntakeReservationAuthorityFacts
                or facts.actor_profile_id != self._context.actor_profile_id
                or facts.identity_link_id != self._context.identity_link_id):
            raise IntakeAuthorityDenied("submission intake is unavailable")
        values = asdict(facts)
        values["resource_id"] = values.pop("operation_id")
        values["scope_project_id"] = values.pop("project_id")
        try:
            return IntakeReservationResourceContext(**values)
        except ValidationError as exc:
            raise IntakeAuthorityDenied("submission intake is unavailable") from exc

    @staticmethod
    def _input(resource: IntakeReservationResourceContext | IntakeAcceptanceResourceContext) -> PreparedAuthorizationInput:
        return PreparedAuthorizationInput(idempotency_key=resource.idempotency_key,
                                          request_value=resource.model_dump(mode="json"))

    async def preflight(self, facts: IntakeReservationPreflightFacts) -> None:
        """Check fresh Submitter authority before eligibility disclosure, with no handle."""
        if (type(facts) is not IntakeReservationPreflightFacts
                or facts.actor_profile_id != self._context.actor_profile_id
                or facts.identity_link_id != self._context.identity_link_id):
            raise IntakeAuthorityDenied("submission intake is unavailable")
        values = asdict(facts)
        values["resource_id"] = values.pop("operation_id")
        values["scope_project_id"] = values.pop("project_id")
        try:
            resource = IntakeReservationPreflightResourceContext(**values)
            value = PreparedAuthorizationInput(idempotency_key=facts.idempotency_key,
                                                request_value=resource.model_dump(mode="json"))
            try:
                await self._prepared.preflight(ActionId.SUBMISSION_INTAKE_RESERVE, value,
                    PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=facts.project_id), resource)
            except PreparedAuthorizationUnsupported as exc:
                await self._prepared.deny_unsupported(ActionId.SUBMISSION_INTAKE_RESERVE, value, resource, exc)
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported, ValidationError) as exc:
            raise IntakeAuthorityDenied("submission intake is unavailable") from exc

    async def prepare(self, facts: IntakeReservationAuthorityFacts) -> object:
        resource = self._resource(facts)
        value = self._input(resource)
        try:
            try:
                return await self._prepared.prepare(ActionId.SUBMISSION_INTAKE_RESERVE, value,
                    PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT,
                                           project_id=resource.scope_project_id))
            except PreparedAuthorizationUnsupported as exc:
                await self._prepared.deny_unsupported(ActionId.SUBMISSION_INTAKE_RESERVE, value, resource, exc)
                raise
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported) as exc:
            raise IntakeAuthorityDenied("submission intake is unavailable") from exc

    async def consume(self, handle: object, facts: IntakeReservationAuthorityFacts) -> UUID:
        resource = self._resource(facts)
        try:
            decision = await self._prepared.consume(handle, ActionId.SUBMISSION_INTAKE_RESERVE,
                                                    self._input(resource), resource)
            return decision.decision_id
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported) as exc:
            raise IntakeAuthorityDenied("submission intake is unavailable") from exc

    @staticmethod
    def _acceptance_resource(facts: IntakeAcceptanceAuthorityFacts) -> IntakeAcceptanceResourceContext:
        if type(facts) is not IntakeAcceptanceAuthorityFacts:
            raise IntakeAuthorityDenied("submission acceptance is unavailable")
        values = asdict(facts)
        values["resource_id"] = values["operation_id"]
        values["scope_project_id"] = values.pop("project_id")
        try:
            return IntakeAcceptanceResourceContext(**values)
        except ValidationError as exc:
            raise IntakeAuthorityDenied("submission acceptance is unavailable") from exc

    def _current_acceptance_resource(self, facts):
        resource = self._acceptance_resource(facts)
        if (not isinstance(self._context, HumanAuthorizationContext)
                or resource.actor_profile_id != self._context.actor_profile_id
                or resource.identity_link_id != self._context.identity_link_id):
            raise IntakeAuthorityDenied("submission acceptance is unavailable")
        return resource

    async def prepare_acceptance(self, facts: IntakeAcceptanceAuthorityFacts) -> object:
        """Prepare fresh submission.create authority for one exact source operation."""
        resource = self._current_acceptance_resource(facts)
        value = self._input(resource)
        try:
            try:
                return await self._prepared.prepare(ActionId.SUBMISSION_CREATE, value,
                    PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT,
                                           project_id=resource.scope_project_id))
            except PreparedAuthorizationUnsupported as exc:
                await self._prepared.deny_unsupported(ActionId.SUBMISSION_CREATE, value, resource, exc)
                raise
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported) as exc:
            raise IntakeAuthorityDenied("submission acceptance is unavailable") from exc

    async def consume_acceptance(self, handle: object, facts: IntakeAcceptanceAuthorityFacts) -> UUID:
        """Consume only the exact prepared acceptance; TASK and ART still own their writes."""
        resource = self._current_acceptance_resource(facts)
        try:
            decision = await self._prepared.consume(handle, ActionId.SUBMISSION_CREATE,
                                                    self._input(resource), resource)
            return decision.decision_id
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported) as exc:
            raise IntakeAuthorityDenied("submission acceptance is unavailable") from exc

    async def validate_acceptance_receipt(self, facts: IntakeAcceptanceAuthorityFacts, decision_id: UUID) -> None:
        """Validate retained provenance after fresh read authority, never renew acceptance.

        Original grant/link status and foreground deadlines may have changed.
        This observation issues no handle and grants no continuation authority.
        """
        resource = self._acceptance_resource(facts)
        if (not self._session.in_transaction() or self._session.in_nested_transaction()
                or not isinstance(self._context, HumanAuthorizationContext)
                or resource.actor_profile_id != self._context.actor_profile_id):
            raise IntakeAuthorityDenied("submission acceptance is unavailable")
        event = await self._kernel._audit.get_authority_event(decision_id)
        expected = {
            "id": str(decision_id), "event_domain": "authority",
            "event_type": "SensitiveAuthorizationAllowed", "actor_ref_kind": "actor_profile",
            "actor_id": str(resource.actor_profile_id), "action_id": ActionId.SUBMISSION_CREATE.value,
            "permission_id": ActionId.SUBMISSION_CREATE.value,
            "project_id": str(resource.scope_project_id), "resource_type": "submission_operation",
            "resource_id": str(resource.operation_id), "target_ref_kind": "project",
            "target_ref_id": str(resource.scope_project_id), "denial_code": None,
            "after_facts": {"allowed": True, "resource_context_digest": authorization_resource_digest(resource)},
        }
        if (event is None or any(getattr(event, key, object()) != value for key, value in expected.items())
                or event.matched_grant_id is None or event.request_id is None or event.correlation_id is None):
            raise IntakeAuthorityDenied("submission acceptance is unavailable")

    async def authorize_read(self, facts: IntakeOperationReadFacts) -> UUID:
        """Read own recorded context under current grant, regardless of task status."""
        if (not self._session.in_transaction() or self._session.in_nested_transaction()
                or type(facts) is not IntakeOperationReadFacts
                or facts.actor_profile_id != self._context.actor_profile_id):
            raise IntakeAuthorityDenied("submission intake is unavailable")
        resource = ContributorWorkReadResourceContext(resource_type="submission_operation_read",
            resource_id=facts.operation_id, actor_profile_id=facts.actor_profile_id,
            scope_project_id=facts.project_id,
            request_digest=canonical_json_hash({key: str(value) for key, value in asdict(facts).items()}))
        try:
            return (await self._kernel.require(ActionId.TASK_SUBMISSION_OPERATION_READ, resource)).decision_id
        except AuthorizationDenied as exc:
            raise IntakeAuthorityDenied("submission intake is unavailable") from exc

    async def restage_denial(self, error: IntakeAuthorityDenied) -> bool:
        """Restage only this request kernel's retained denial after root rollback."""
        if isinstance(error.__cause__, AuthorizationDenied):
            await self._kernel.restage_denial(error.__cause__.decision)
            return True
        return False

    def close(self) -> None:
        self._prepared.close()
