"""Fixed post-submit principals through canonical AUTH/PREP and exact consumer contracts."""

from contextlib import asynccontextmanager, contextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.domain.post_submit import (
    EXECUTE, FINALIZE, MATERIALIZE, post_submit_digest, post_submit_prepare_values,
    post_submit_request, post_submit_resource,
)
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import (
    AuthorizationDenied, AuthorizationEvidenceUnavailable, PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput, PreparedAuthorizationUnsupported, PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, ExecuteEvidence, FinalizeEvidence,
    PreparedExecution, PreparedFinalization,
)
from app.modules.checkers.api.materialization import (
    PreparedMaterialization, PostSubmissionMaterializationUnavailable,
)
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationRequest


@contextmanager
def _authority_errors(action):
    """Conceal AUTH failures without swallowing protected-owner errors."""
    try:
        yield
    except (AuthorizationDenied, AuthorizationEvidenceUnavailable, PreparedAuthorizationHandleInvalid,
            PreparedAuthorizationUnsupported) as error:
        exception = PostSubmissionMaterializationUnavailable if action == MATERIALIZE else CheckerExecutionUnavailable
        raise exception("post_submit_authority_unavailable") from error


class _PreparedPhase:
    """Only shared PREP owns handle lifetime and one-use/transaction enforcement."""

    def __init__(self, service, handle, caller_input, action):
        self._service, self._handle, self._input, self._action = service, handle, caller_input, action

    async def _consume(self, facts):
        with _authority_errors(self._action):
            return await self._service.consume(
                self._handle, self._action, self._input, post_submit_resource(self._action, facts),
            )

    async def validate_replay(self, facts, evidence_id):
        with _authority_errors(self._action):
            await self._service.validate_replay(
                self._handle, self._action, self._input,
                post_submit_resource(self._action, facts), evidence_id,
            )


class _PreparedExecute(_PreparedPhase, PreparedExecution):
    async def consume(self, facts):
        decision = await self._consume(facts)
        return ExecuteEvidence(evidence_id=decision.decision_id, facts_digest=post_submit_digest(facts))


class _PreparedFinalize(_PreparedPhase, PreparedFinalization):
    async def consume(self, facts):
        decision = await self._consume(facts)
        return FinalizeEvidence(evidence_id=decision.decision_id, facts_digest=post_submit_digest(facts))


class _PreparedMaterialize(_PreparedPhase, PreparedMaterialization):
    async def consume(self, facts):
        return (await self._consume(facts)).decision_id


@asynccontextmanager
async def _prepare(session, action, request, *, execution=None):
    """Acquire fixed principal custody before any CHECKERS or ART feature locks."""
    try:
        PostSubmissionEvaluationRequest.model_validate_json(request.model_dump_json())
        prepare_values = post_submit_prepare_values(action, request, execution)
    except (AttributeError, ValueError, TypeError) as error:
        exception = PostSubmissionMaterializationUnavailable if action == MATERIALIZE else CheckerExecutionUnavailable
        raise exception("post_submit_authority_unavailable") from error
    identity = ServiceIdentity.ARTIFACT_MATERIALIZER if action == MATERIALIZE else ServiceIdentity.CHECKER_POST_SUBMIT
    prepared_type = {EXECUTE: _PreparedExecute, FINALIZE: _PreparedFinalize, MATERIALIZE: _PreparedMaterialize}[action]
    with _authority_errors(action):
        async with fixed_service_prepared_authorization(
            session, service_identity=identity, request_id=request.evaluation_request_id,
            correlation_id=request.evaluation_request_id,
        ) as authority:
            caller_input = PreparedAuthorizationInput(
                idempotency_key=request.evaluation_request_id,
                request_value=prepare_values,
            )
            handle = await authority.service.prepare(action, caller_input, PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT, project_id=request.project_id,
            ))
            yield prepared_type(authority.service, handle, caller_input, action)


class PostSubmitExecutionAuthorization:
    """Expose the two exact checker operations without selectable service identity."""

    def __init__(self, session):
        self._session = session

    async def preflight(self, request):
        """Validate value shape; preparation admits and locks the live principal before owner access."""
        PostSubmissionEvaluationRequest.model_validate_json(request.model_dump_json())

    def prepare_execution(self, request):
        return _prepare(self._session, EXECUTE, request)

    def prepare_finalization(self, request):
        return _prepare(self._session, FINALIZE, request)


class PostSubmitMaterializationAuthorization:
    """Give the fixed materializer only exact current submitted-byte read authority."""

    def __init__(self, session):
        self._session = session

    def prepare_materialization(self, facts):
        return _prepare(self._session, MATERIALIZE, post_submit_request(facts), execution=facts)
