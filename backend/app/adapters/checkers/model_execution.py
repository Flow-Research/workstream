"""Compose optional project-image model callbacks into the sole POST execution path."""

from typing import Literal

from app.interfaces.external_services import ExternalServiceUnavailableError
from app.modules.model_usage.api import (
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
)
from app.modules.checkers.api.model_profiles import configured_model_profile_selector


def model_execution_facts(request) -> ModelCallExecutionFacts:
    """Translate the existing typed POST identity without inventing new lineage."""
    identity = request.identity
    if identity.phase != "post_submit":
        raise ModelCallUnavailable("model_call_execution_unavailable")
    return ModelCallExecutionFacts(
        project_id=identity.project_id,
        task_id=identity.task_id,
        assignment_id=identity.assignment_id,
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        evaluation_request_id=identity.evaluation_request_id,
        evaluation_generation=identity.evaluation_generation,
        checker_run_id=identity.attempt_id,
        worker_lease_id=identity.lease_id,
        worker_lease_generation=identity.lease_generation,
        worker_lease_expires_at=identity.lease_expires_at,
    )


class ModelAwareExternalExecution:
    """Grant one private model callback and verify its completion before a verdict."""

    def __init__(self, *, execution, sessions):
        self._execution, self._sessions = execution, sessions

    @property
    def identity(self):
        """Keep the same fixed Rust provider identity."""
        return self._execution.identity

    @property
    def pre_runtime_provider(self) -> Literal["smolvm", "managed"]:
        """Preserve the selected execution adapter's PRE evidence family."""
        return self._execution.pre_runtime_provider

    async def health(self):
        """Use the existing external execution health contract."""
        return await self._execution.health()

    async def execute_pre(self, lease, grant):
        """PRE receives no model authority or paid slot from this POST wrapper."""
        return await self._execution.execute_pre(lease, grant)

    async def locate_forge_change(self, request, grant):
        """Locator gets no model grant, paid slot or trial callback."""
        return await self._execution.locate_forge_change(request, grant)

    async def execute(self, request, grant, *, model_grant=None):
        """Ordinary images run directly; model images must complete their exact call."""
        from app.adapters.auth import checker_model_service_authorization
        from app.adapters.checkers import model_call_service, model_invocation_grants

        if model_grant is not None:
            raise ExternalServiceUnavailableError(self.identity)
        selector = configured_model_profile_selector(
            request.configuration,
            stage=request.identity.phase,
        )
        if selector is None:
            return await self._execution.execute(request, grant)
        facts = model_execution_facts(request)
        slot = ModelPaidSlotKey(
            project_id=facts.project_id,
            assignment_id=facts.assignment_id,
            submission_id=facts.submission_id,
            submission_version=facts.submission_version,
            requirement_id=request.input.get("requirement_id"),
            registry_entry_digest=request.registry.entry_digest,
            configuration_sha256=request.configuration_sha256,
            profile_id=selector.profile_id,
            profile_version=selector.profile_version,
            profile_digest=selector.profile_digest,
        )
        try:
            async with self._sessions() as session, session.begin():
                authority = await checker_model_service_authorization(
                    session, facts.evaluation_request_id
                )
                callback = await model_invocation_grants(session, authority).issue(
                    facts,
                    slot,
                    request.request_digest,
                    registry_entry_id=request.registry.registry_entry_id,
                )
            response = await self._execution.execute(request, grant, model_grant=callback)
            if response.result.outcome == "completed":
                async with self._sessions() as session, session.begin():
                    authority = await checker_model_service_authorization(
                        session, facts.evaluation_request_id
                    )
                    effects = await model_invocation_grants(session, authority).completed_effects(
                        callback.grant_id,
                        request.request_digest,
                        facts,
                    )
                    calls = model_call_service(session, authority)
                    for effect in effects:
                        await calls.attach_completed(facts, effect)
            return response
        except ModelCallUnavailable as error:
            raise ExternalServiceUnavailableError(self.identity) from error
