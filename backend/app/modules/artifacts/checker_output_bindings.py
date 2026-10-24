"""Verified checker-output bindings in the caller's final-result transaction."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.modules.artifacts.api.checker_output_authority import (
    CheckerOutputBindingAuthority,
)
from app.modules.checkers.api.output_custody import (
    CheckerOutputBindingRequest,
    CheckerOutputBindingResult,
    CheckerOutputReservationPort,
    GENERATED_OUTPUT_SELECTOR,
    generated_output_subject,
    CheckerOutputUnavailable,
)
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceBindingRequest,
    TrialEvidenceCustodyAck,
    TrialEvidenceReservationPort,
)
from app.modules.model_usage.api import (
    SetupModelOutputBindingRequest,
    SetupModelOutputBindingResult,
    SetupModelOutputReservationPort,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.artifacts.checker_output_custody import select_checker_output
from app.modules.artifacts.models import ArtifactBinding


class CheckerOutputBindingService:
    """Flush one immutable binding; never commit the caller's result transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        reservations: CheckerOutputReservationPort | TrialEvidenceReservationPort | SetupModelOutputReservationPort,
        authority: CheckerOutputBindingAuthority,
        namespace_fingerprint: str,
    ) -> None:
        self._session, self._reservations, self._authority = session, reservations, authority
        self._namespace_fingerprint = namespace_fingerprint

    async def bind_checker_output(
        self, request: CheckerOutputBindingRequest
    ) -> CheckerOutputBindingResult:
        """Bind exact model-call evidence through the shared publication operation."""
        if type(request) is not CheckerOutputBindingRequest:
            raise TypeError("invalid checker output binding request")
        return await self._bind(request)

    async def bind_trial_evidence(
        self,
        request: TrialEvidenceBindingRequest,
    ) -> TrialEvidenceCustodyAck:
        """Bind exact trial evidence without committing the caller transaction."""
        if type(request) is not TrialEvidenceBindingRequest:
            raise TypeError("invalid trial evidence binding request")
        return await self._bind(request)

    async def bind_setup_output(
        self, request: SetupModelOutputBindingRequest
    ) -> SetupModelOutputBindingResult:
        if type(request) is not SetupModelOutputBindingRequest:
            raise TypeError("invalid setup model output binding request")
        result = await self._bind(request)
        return SetupModelOutputBindingResult(
            result.binding_id,
            result.content_id,
            result.put_attempt_id,
            result.verification_receipt_id,
            result.replayed,
        )

    async def _bind(
        self,
        request: CheckerOutputBindingRequest | TrialEvidenceBindingRequest | SetupModelOutputBindingRequest,
    ) -> CheckerOutputBindingResult | TrialEvidenceCustodyAck:
        """Fence current worker facts before acquiring ART binding/verification locks."""
        if (
            not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or type(request.put_attempt_id) is not UUID
            or type(request.verification_receipt_id) is not UUID
        ):
            raise CheckerOutputUnavailable("checker_output_binding_unavailable")
        selector = GENERATED_OUTPUT_SELECTOR.validate_python(request.selector)
        try:
            await self._authority.preflight(selector)
            await self._authority.prepare(selector)
            reservation = await self._reservations.resolve(selector)
            reservation.select(selector)
            owner = generated_output_subject(reservation)
            await self._session.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": f"checker-output:{owner.project_id}:{owner.resource_id}:{owner.logical_role}",
                },
            )
            facts = await select_checker_output(
                self._session,
                selector=selector,
                reservation=reservation,
                namespace_fingerprint=self._namespace_fingerprint,
                put_attempt_id=request.put_attempt_id,
                verification_receipt_id=request.verification_receipt_id,
                lock_verified=True,
            )
            if (
                facts is None
                or facts.status != "verified"
                or facts.verification_receipt_id != request.verification_receipt_id
            ):
                raise CheckerOutputUnavailable("checker_output_verification_unavailable")
            await self._authority.consume(reservation, facts)
            binding = await self._session.scalar(
                select(ArtifactBinding)
                .where(
                    ArtifactBinding.project_id == str(owner.project_id),
                    ArtifactBinding.resource_type == owner.resource_type,
                    ArtifactBinding.resource_id == str(owner.resource_id),
                    ArtifactBinding.logical_role == owner.logical_role,
                    ArtifactBinding.scope_version == 1,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            replayed = binding is not None
            if binding is not None:
                if (
                    binding.content_id,
                    binding.put_attempt_id,
                    binding.verification_receipt_id,
                    binding.actor_id,
                    binding.attribution_type,
                ) != (
                    str(facts.content_id),
                    str(facts.put_attempt_id),
                    str(facts.verification_receipt_id),
                    ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                    "service_identity",
                ):
                    raise CheckerOutputUnavailable("checker_output_binding_conflict")
            else:
                binding = ArtifactBinding(
                    id=str(new_record_id()),
                    content_id=str(facts.content_id),
                    project_id=str(owner.project_id),
                    resource_type=owner.resource_type,
                    resource_id=str(owner.resource_id),
                    logical_role=owner.logical_role,
                    scope_version=1,
                    actor_id=ServiceIdentity.ARTIFACT_CHECKER_OUTPUT.value,
                    attribution_type="service_identity",
                    supersedes_binding_id=None,
                    put_attempt_id=str(facts.put_attempt_id),
                    verification_receipt_id=str(facts.verification_receipt_id),
                )
                self._session.add(binding)
                await self._session.flush()
            if isinstance(request, TrialEvidenceBindingRequest):
                return TrialEvidenceCustodyAck(
                    trial_evidence_id=selector.trial_evidence_id,
                    owner_digest=reservation.owner_digest,
                    content_sha256=facts.sha256,
                    byte_count=facts.byte_count,
                    binding_id=UUID(binding.id),
                    content_id=UUID(binding.content_id),
                    put_attempt_id=request.put_attempt_id,
                    verification_receipt_id=request.verification_receipt_id,
                    replayed=replayed,
                )
            return CheckerOutputBindingResult(
                UUID(binding.id),
                UUID(binding.content_id),
                request.put_attempt_id,
                request.verification_receipt_id,
                replayed,
            )
        finally:
            self._authority.discard()
