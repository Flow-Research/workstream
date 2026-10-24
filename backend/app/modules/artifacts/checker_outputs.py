"""Bounded checker bytes through the existing durable ART storage workflow."""

import hashlib
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.interfaces.artifacts import ArtifactByteRange, ArtifactIntegrityError, ArtifactStore
from app.modules.artifacts.api.checker_output_authority import (
    CheckerOutputWriteAuthority,
)
from app.modules.artifacts.checker_output_custody import select_checker_output
from app.modules.artifacts.models import ArtifactBinding, ArtifactReplica, ArtifactVerificationJob
from app.modules.artifacts.preparation import ArtifactPreparationService
from app.modules.artifacts.schemas import (
    ArtifactInternalAuthority,
    CheckerOutputArtifactAdmissionRequest,
)
from app.modules.artifacts.service import (
    ArtifactAdmissionService,
    ArtifactStorageNamespaceSpec,
    ArtifactStorageOrchestrator,
)
from app.modules.checkers.api.output_custody import (
    GENERATED_OUTPUT_SELECTOR,
    CheckerOutputArtifactRequest,
    CheckerOutputArtifactResult,
    CheckerOutputReservationPort,
    CheckerOutputSelector,
    CheckerOutputUnavailable,
    GeneratedOutputSelector,
)
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceArtifactRequest,
    TrialEvidenceCustodyAck,
    TrialEvidenceSelector,
    TrialEvidenceReservationPort,
)
from app.modules.model_usage.api import (
    ModelCallEvidence,
    SetupModelOutputArtifactRequest,
    SetupModelOutputArtifactResult,
    SetupModelOutputReservationPort,
    SetupModelOutputSelector,
)


class CheckerArtifactOutputService:
    """Own preparation lifetime; reuse put/observation and independent verification."""

    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        reservations: Callable[
            [AsyncSession], CheckerOutputReservationPort | TrialEvidenceReservationPort | SetupModelOutputReservationPort
        ],
        authority: Callable[[AsyncSession], CheckerOutputWriteAuthority],
        internal_authority: Callable[[AsyncSession], ArtifactInternalAuthority],
        verification_authority: Callable[[AsyncSession], ArtifactInternalAuthority],
        preparation: ArtifactPreparationService,
        store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec,
        settings: Settings,
    ) -> None:
        self._sessions, self._reservations, self._authority = sessions, reservations, authority
        self._internal_authority, self._preparation = internal_authority, preparation
        self._verification_authority = verification_authority
        self._store, self._namespace, self._settings = store, namespace, settings

    async def store(self, request: CheckerOutputArtifactRequest) -> CheckerOutputArtifactResult:
        """Commit checked output bytes before I/O, never a CHECKERS completion."""
        if type(request) is not CheckerOutputArtifactRequest:
            raise TypeError("invalid checker output request")
        return await self._store_output(request)

    async def store_trial_evidence(
        self,
        request: TrialEvidenceArtifactRequest,
    ) -> CheckerOutputArtifactResult:
        """Use the same bounded put and verification workflow for a trial receipt."""
        if type(request) is not TrialEvidenceArtifactRequest:
            raise TypeError("invalid trial evidence artifact request")
        return await self._store_output(request)

    async def store_setup_output(
        self, request: SetupModelOutputArtifactRequest
    ) -> SetupModelOutputArtifactResult:
        """Store setup request/response bytes through the same verified path."""
        if type(request) is not SetupModelOutputArtifactRequest:
            raise TypeError("invalid setup model output request")
        result = await self._store_output(request)
        return SetupModelOutputArtifactResult(
            result.put_attempt_id,
            result.status,
            result.content_id,
            result.verification_receipt_id,
            result.content_sha256,
            result.byte_count,
            result.replayed,
        )

    async def _store_output(
        self,
        request: CheckerOutputArtifactRequest | TrialEvidenceArtifactRequest | SetupModelOutputArtifactRequest,
    ) -> CheckerOutputArtifactResult:
        """Prepare outside custody, then atomically admit exact owner content."""
        selector = GENERATED_OUTPUT_SELECTOR.validate_python(request.selector)
        prepared = None
        async with self._sessions() as session:
            authority = self._authority(session)
            try:
                await authority.preflight(selector)
                async with session.begin():
                    await authority.prepare(selector)
                    reservation = await self._reservations(session).resolve(selector)
                    slot = reservation.select(selector)
                authority.discard()
                prepared = await self._preparation.prepare(
                    request.byte_source,
                    media_type=slot.media_type,
                    maximum_bytes=slot.maximum_bytes,
                )
                async with session.begin():
                    await authority.prepare(selector)
                    reservations = self._reservations(session)
                    current = (
                        await reservations.pin_content(selector)
                        if isinstance(selector, TrialEvidenceSelector)
                        else await reservations.resolve(selector)
                    )
                    if current.select(selector) != slot:
                        raise CheckerOutputUnavailable("checker_output_slot_changed")
                    admission = await ArtifactAdmissionService(
                        session, self._settings, self._namespace
                    ).admit(
                        CheckerOutputArtifactAdmissionRequest(
                            reservation=current,
                            slot_key=slot.key,
                            source=prepared.committed_source,
                        ),
                        checker_output_authority=authority,
                        existing_transaction=True,
                    )
                authority.discard()
                storage = self._storage(session)
                if admission.status == "object_confirmed":
                    status = admission.status
                elif admission.replayed:
                    status = await storage.resume_committed_put(
                        attempt_id=admission.attempt_id,
                        source=prepared.committed_source,
                    )
                else:
                    status = await storage.execute_committed_put(
                        attempt_id=admission.attempt_id,
                        source=prepared.committed_source,
                    )
                await self._verify(session, storage, admission.attempt_id, status)
                return await self._result(session, authority, selector, replayed=admission.replayed)
            finally:
                authority.discard()
                if prepared is not None:
                    await prepared.close()

    async def recover(self, selector: CheckerOutputSelector) -> CheckerOutputArtifactResult | None:
        """Recover a lost response by logical identity without regenerating bytes."""
        return await self._recover(CheckerOutputSelector.model_validate(selector))

    async def recover_trial_evidence(
        self,
        selector: TrialEvidenceSelector,
    ) -> CheckerOutputArtifactResult | None:
        """Recover the original trial put after a lost acknowledgement."""
        return await self._recover(TrialEvidenceSelector.model_validate(selector))

    async def recover_setup_output(
        self, selector: SetupModelOutputSelector
    ) -> SetupModelOutputArtifactResult | None:
        result = await self._recover(SetupModelOutputSelector.model_validate(selector))
        return (
            None
            if result is None
            else SetupModelOutputArtifactResult(
                result.put_attempt_id,
                result.status,
                result.content_id,
                result.verification_receipt_id,
                result.content_sha256,
                result.byte_count,
                result.replayed,
            )
        )

    async def _recover(
        self,
        selector: GeneratedOutputSelector,
    ) -> CheckerOutputArtifactResult | None:
        """Resolve the one retained put through fresh owner and action custody."""
        async with self._sessions() as session:
            authority = self._authority(session)
            try:
                await authority.preflight(selector)
                async with session.begin():
                    await authority.prepare(selector)
                    reservation = await self._reservations(session).resolve(selector)
                    reservation.select(selector)
                    facts = await select_checker_output(
                        session,
                        selector=selector,
                        reservation=reservation,
                        namespace_fingerprint=self._namespace.namespace_fingerprint,
                    )
                    if facts is None:
                        return None
                    await authority.consume_existing(reservation, facts)
                authority.discard()
                storage = self._storage(session)
                status = facts.status
                if status not in {"object_confirmed", "verified"}:
                    status = await storage.resolve_put_attempt(facts.put_attempt_id)
                await self._verify(session, storage, facts.put_attempt_id, status)
                return await self._result(session, authority, selector, replayed=True)
            finally:
                authority.discard()

    async def read_response(
        self,
        selector: CheckerOutputSelector,
        evidence: ModelCallEvidence,
    ) -> bytes:
        """Read only exact private response evidence, bounded and independently hashed."""
        selector = CheckerOutputSelector.model_validate(selector)
        evidence = ModelCallEvidence.model_validate(evidence)
        if (
            selector.slot_key != "model_response"
            or selector.content_sha256 != evidence.content_sha256
        ):
            raise CheckerOutputUnavailable("checker_output_response_unavailable")
        return await self._read(selector, evidence)

    async def read_trial_evidence(
        self,
        selector: TrialEvidenceSelector,
        evidence: TrialEvidenceCustodyAck,
    ) -> bytes:
        """Read only the bound original trial receipt under fresh execution custody."""
        selector = TrialEvidenceSelector.model_validate(selector)
        evidence = TrialEvidenceCustodyAck.model_validate(evidence)
        if (selector.trial_evidence_id, selector.content_sha256) != (
            evidence.trial_evidence_id,
            evidence.content_sha256,
        ):
            raise CheckerOutputUnavailable("checker_output_response_unavailable")
        return await self._read(selector, evidence)

    async def read_setup_response(
        self, selector: SetupModelOutputSelector, evidence: ModelCallEvidence
    ) -> bytes:
        selector = SetupModelOutputSelector.model_validate(selector)
        evidence = ModelCallEvidence.model_validate(evidence)
        if selector.role != "model_response" or selector.content_sha256 != evidence.content_sha256:
            raise CheckerOutputUnavailable("checker_output_response_unavailable")
        return await self._read(selector, evidence)

    async def _read(
        self,
        selector: GeneratedOutputSelector,
        evidence: ModelCallEvidence | TrialEvidenceCustodyAck,
    ) -> bytes:
        """Recheck exact verified ancestry and bounded bytes before releasing evidence."""
        media_type = (
            evidence.media_type if isinstance(evidence, ModelCallEvidence) else "application/json"
        )
        async with self._sessions() as session:
            authority = self._authority(session)
            try:
                await authority.preflight(selector)
                async with session.begin():
                    await authority.prepare(selector)
                    reservation = await self._reservations(session).resolve(selector)
                    if isinstance(evidence, TrialEvidenceCustodyAck):
                        await self._require_trial_binding(session, reservation, evidence)
                    facts = await select_checker_output(
                        session,
                        selector=selector,
                        reservation=reservation,
                        namespace_fingerprint=self._namespace.namespace_fingerprint,
                        put_attempt_id=evidence.put_attempt_id,
                        verification_receipt_id=evidence.verification_receipt_id,
                    )
                    if (
                        facts is None
                        or facts.status != "verified"
                        or (
                            facts.content_id,
                            facts.sha256,
                            facts.byte_count,
                            facts.media_type,
                        )
                        != (
                            evidence.content_id,
                            evidence.content_sha256,
                            evidence.byte_count,
                            media_type,
                        )
                    ):
                        raise CheckerOutputUnavailable("checker_output_response_unavailable")
                    await authority.consume_existing(reservation, facts)
                    provider_ref = await session.scalar(
                        select(ArtifactReplica.provider_object_ref).where(
                            ArtifactReplica.id == str(facts.replica_id),
                            ArtifactReplica.namespace_fingerprint
                            == self._namespace.namespace_fingerprint,
                        )
                    )
                    if provider_ref is None:
                        raise CheckerOutputUnavailable("checker_output_response_unavailable")
                authority.discard()
                data = bytearray()
                async for chunk in self._store.open(
                    provider_ref,
                    byte_range=ArtifactByteRange(length=evidence.byte_count + 1),
                ):
                    data.extend(chunk)
                    if len(data) > evidence.byte_count:
                        raise ArtifactIntegrityError("checker evidence length mismatch")
                if len(data) != evidence.byte_count or (
                    "sha256:" + hashlib.sha256(data).hexdigest() != evidence.content_sha256
                ):
                    raise ArtifactIntegrityError("checker evidence digest mismatch")
                # Revocation and owner substitution during provider I/O still deny release.
                current = await self._result(session, authority, selector, replayed=True)
                if (current.content_id, current.verification_receipt_id) != (
                    evidence.content_id,
                    evidence.verification_receipt_id,
                ):
                    raise CheckerOutputUnavailable("checker_output_response_unavailable")
                return bytes(data)
            finally:
                authority.discard()

    async def _require_trial_binding(self, session, reservation, evidence) -> None:
        """Match every immutable binding coordinate and the owner receipt digest."""
        binding = await session.get(ArtifactBinding, str(evidence.binding_id))
        if (
            reservation.owner_digest != evidence.owner_digest
            or binding is None
            or (
                binding.project_id,
                binding.resource_type,
                binding.resource_id,
                binding.logical_role,
                binding.scope_version,
                binding.content_id,
                binding.put_attempt_id,
                binding.verification_receipt_id,
            )
            != (
                str(reservation.subject.project_id),
                "checker_trial_evidence",
                str(evidence.trial_evidence_id),
                "trial_receipt",
                1,
                str(evidence.content_id),
                str(evidence.put_attempt_id),
                str(evidence.verification_receipt_id),
            )
        ):
            raise CheckerOutputUnavailable("checker_output_response_unavailable")

    def _storage(self, session: AsyncSession) -> ArtifactStorageOrchestrator:
        """Use the shared put, observation and verification implementation."""
        return ArtifactStorageOrchestrator(
            session, self._store, self._namespace, self._settings, self._internal_authority(session)
        )

    async def _verify(
        self,
        session: AsyncSession,
        storage: ArtifactStorageOrchestrator,
        attempt_id: UUID,
        status: str,
    ) -> None:
        """Independently verify confirmed bytes through the existing ART worker."""
        if status not in {
            "object_confirmed",
            "verified",
            "stored_pending_verification",
            "observed_confirmed",
        }:
            return
        async with session.begin():
            job_id = await session.scalar(
                select(ArtifactVerificationJob.id)
                .where(
                    ArtifactVerificationJob.originating_put_attempt_id == str(attempt_id),
                    ArtifactVerificationJob.status == "pending",
                )
                .order_by(ArtifactVerificationJob.id)
                .limit(1)
            )
        if job_id is not None:
            verifier = ArtifactStorageOrchestrator(
                session,
                self._store,
                self._namespace,
                self._settings,
                self._verification_authority(session),
            )
            await verifier.verify_object(UUID(job_id))

    async def _result(
        self,
        session: AsyncSession,
        authority: CheckerOutputWriteAuthority,
        selector: GeneratedOutputSelector,
        *,
        replayed: bool,
    ) -> CheckerOutputArtifactResult:
        """Recheck current owner custody and authority after provider operations."""
        async with session.begin():
            await authority.prepare(selector)
            reservation = await self._reservations(session).resolve(selector)
            reservation.select(selector)
            facts = await select_checker_output(
                session,
                selector=selector,
                reservation=reservation,
                namespace_fingerprint=self._namespace.namespace_fingerprint,
            )
            if facts is None:
                raise CheckerOutputUnavailable("checker_output_unavailable")
            await authority.consume_existing(reservation, facts)
            return CheckerOutputArtifactResult(
                facts.put_attempt_id,
                facts.status,
                facts.content_id,
                facts.verification_receipt_id,
                facts.sha256,
                facts.byte_count,
                replayed,
            )
