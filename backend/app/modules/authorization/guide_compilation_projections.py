"""Purpose-specific fixed-service adapters for compilation projections."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from copy import Error as CopyError
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    AuthorizationDenied,
    AuthorizationUnavailable,
    GuideSufficiencyProjectionFacts,
    PreparedAuthorizationInvalid,
    PreparedArtifactPolicyProjection,
    PreparedGuideSufficiencyProjection,
    ProjectGuideProjectionAuthorityReceipt,
    ProjectGuideProjectionIdentity,
    ProjectGuideProjectionLocator,
    artifact_policy_projection_identity,
    guide_sufficiency_projection_identity,
)
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectionComponent,
    projection_action,
    projection_prepare_context,
    projection_resource_context,
    projection_resource_digest,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationHandle,
    fixed_service_prepared_authorization,
)
from app.modules.authorization.runtime import (
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)

_ZERO = UUID(int=0)


class _PreparedProjection:
    """Nominal non-serializable view over one existing PREP handle."""

    __slots__ = (
        "_component",
        "_custody",
        "_handle",
        "_input",
        "_identity",
        "_locator",
    )

    def __init__(
        self,
        component: ProjectionComponent,
        custody: FixedServicePreparedAuthorization,
        handle: PreparedAuthorizationHandle,
        caller_input: PreparedAuthorizationInput,
        identity: ProjectGuideProjectionIdentity,
        locator: ProjectGuideProjectionLocator,
    ) -> None:
        self._component = component
        self._custody = custody
        self._handle = handle
        self._input = caller_input
        self._identity = identity
        self._locator = locator

    @property
    def identity(self) -> ProjectGuideProjectionIdentity:
        return self._identity

    def __copy__(self) -> NoReturn:
        raise CopyError("prepared projection authority cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise CopyError("prepared projection authority cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("prepared projection authority cannot be serialized")

    def _resource(self, facts):
        try:
            resource = projection_resource_context(self._component, self._identity, facts)
        except (TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        if (
            resource.scope_project_id != self._locator.project_id
            or UUID(str(resource.projection_facts["attempt_id"])) != self._locator.attempt_id
        ):
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid")
        return resource

    async def consume_new(
        self, facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts
    ) -> ProjectGuideProjectionAuthorityReceipt:
        resource = self._resource(facts)
        try:
            decision = await self._custody.service.consume(
                self._handle,
                projection_action(self._component),
                self._input,
                resource,
            )
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        except PreparedAuthorizationUnsupported as exc:
            raise AuthorizationDenied("projection authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("projection authority unavailable") from exc
        return ProjectGuideProjectionAuthorityReceipt(
            decision_event_id=decision.decision_id,
            actor_profile_id=self._identity.actor_profile_id,
            identity_link_id=self._identity.identity_link_id,
            service_identity=self._identity.service_identity,
            resource_context_digest=projection_resource_digest(resource),
        )

    async def validate_replay(
        self,
        facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
        stored_decision_id: UUID,
    ) -> None:
        resource = self._resource(facts)
        try:
            await self._custody.service.validate_replay(
                self._handle,
                projection_action(self._component),
                self._input,
                resource,
                stored_decision_id,
            )
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        except PreparedAuthorizationUnsupported as exc:
            raise AuthorizationDenied("projection authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("projection authority unavailable") from exc


class _ProjectionAuthorization:
    def __init__(self, session: AsyncSession, component: ProjectionComponent) -> None:
        self._session = session
        self._component = component

    def _identity(self, attempt_id: UUID, actor: UUID, link: UUID):
        helper = (
            guide_sufficiency_projection_identity
            if self._component == "guide_sufficiency"
            else artifact_policy_projection_identity
        )
        return helper(
            attempt_id=attempt_id,
            actor_profile_id=actor,
            identity_link_id=link,
        )

    @asynccontextmanager
    async def _prepare(self, locator: ProjectGuideProjectionLocator):
        seed = self._identity(locator.attempt_id, _ZERO, _ZERO)
        manager = fixed_service_prepared_authorization(
            self._session,
            service_identity=ServiceIdentity.PROJECT_SETUP,
            request_id=seed.operation_id,
            correlation_id=seed.correlation_id,
        )
        try:
            custody = await manager.__aenter__()
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        except PreparedAuthorizationUnsupported as exc:
            raise AuthorizationDenied("projection authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("projection authority unavailable") from exc
        try:
            try:
                identity = self._identity(
                    locator.attempt_id,
                    custody.actor_profile_id,
                    custody.identity_link_id,
                )
                prepare = projection_prepare_context(self._component, locator, identity)
                caller_input = PreparedAuthorizationInput(
                    idempotency_key=identity.operation_id,
                    request_value=prepare.model_dump(mode="json"),
                )
                handle = await custody.service.prepare(
                    projection_action(self._component),
                    caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT,
                        project_id=locator.project_id,
                    ),
                )
            except PreparedAuthorizationHandleInvalid as exc:
                raise PreparedAuthorizationInvalid(
                    "prepared projection authority is invalid"
                ) from exc
            except PreparedAuthorizationUnsupported as exc:
                raise AuthorizationDenied("projection authority denied") from exc
            except AuthorizationEvidenceUnavailable as exc:
                raise AuthorizationUnavailable("projection authority unavailable") from exc
            yield _PreparedProjection(
                self._component,
                custody,
                handle,
                caller_input,
                identity,
                locator,
            )
        finally:
            try:
                await manager.__aexit__(None, None, None)
            except PreparedAuthorizationHandleInvalid as exc:
                raise PreparedAuthorizationInvalid(
                    "prepared projection authority is invalid"
                ) from exc
            except PreparedAuthorizationUnsupported as exc:
                raise AuthorizationDenied("projection authority denied") from exc
            except AuthorizationEvidenceUnavailable as exc:
                raise AuthorizationUnavailable("projection authority unavailable") from exc


class GuideSufficiencyProjectionAuthorization(_ProjectionAuthorization):
    """Prepare only fixed-service guide-sufficiency projection authority."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, "guide_sufficiency")

    def prepare_sufficiency_projection(
        self, locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedGuideSufficiencyProjection]:
        return self._prepare(locator)


class ArtifactPolicyProjectionAuthorization(_ProjectionAuthorization):
    """Prepare only fixed-service artifact-policy projection authority."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, "submission_artifact_policy")

    def prepare_artifact_policy_projection(
        self, locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedArtifactPolicyProjection]:
        return self._prepare(locator)
