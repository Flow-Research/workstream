"""Durable trial reservation under current TASK and selected CHECKERS custody."""

import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.interfaces.trial_execution import TrialProfileReaderPort
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, EvaluationTaskGuard, ExecuteEvidence, ExecuteFacts,
    ExecutionAuthorityPort, ExecutionLease, execution_authority_digest,
)
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest, PostSubmitExternalCheckerIdentity,
    external_checker_json_hash,
)
from app.modules.checkers.api.trial_evidence import (
    TrialEvidenceOrigin, TrialEvidenceReservation, TrialEvidenceSelector,
    TrialEvidenceSlot, TrialEvidenceStableSubject, TrialEvidenceTicket,
    TrialEvidenceUnavailable,
)
from app.modules.checkers.api.trial_profiles import (
    TrialAuthorityContext,
    trial_selector_from_configuration,
)
from app.modules.checkers.execution_repository import (
    ExecutionRepository, require_transaction, reservation, stored_request,
)
from app.modules.checkers.models import CheckerRun, CheckerTrialEvidence


def _value(model, body):
    """Revalidate retained UUID-bearing JSON through the strict public contract."""
    return model.model_validate_json(json.dumps(body, separators=(",", ":")))


class TrialEvidenceReservations:
    """Keep exact replay stable while every access qualifies the current invocation."""

    def __init__(
        self, session: AsyncSession, *, request: ExternalCheckerExecutionRequest,
        tasks: EvaluationTaskGuard, profiles: TrialProfileReaderPort,
        authority: ExecutionAuthorityPort,
    ):
        """Bind a caller-owned transaction to one validated POST execution request."""
        self._session = session
        self._request = ExternalCheckerExecutionRequest.model_validate(request)
        self._tasks, self._profiles, self._authority = tasks, profiles, authority
        if not isinstance(self._request.identity, PostSubmitExternalCheckerIdentity):
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")

    async def _request_facts(self):
        """Read immutable request provenance before acquiring any feature lock."""
        require_transaction(self._session)
        identity = self._request.identity
        run = await self._session.get(CheckerRun, str(identity.attempt_id))
        if run is None:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        request = stored_request(run)
        if (
            request.project_id, request.task_id, request.assignment_id,
            request.submission_id, request.submission_version,
            request.evaluation_request_id, request.evaluation_generation,
            request.request_sha256,
        ) != (
            identity.project_id, identity.task_id, identity.assignment_id,
            identity.submission_id, identity.submission_version,
            identity.evaluation_request_id, identity.evaluation_generation,
            identity.evaluation_request_digest,
        ):
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        bindings = [entry for entry in request.policy.entries if (
            entry.requirement_id == self._request.input.get("requirement_id")
            and entry.registry == self._request.registry
            and entry.configuration == self._request.configuration
            and entry.configuration_sha256 == self._request.configuration_sha256
        )]
        if len(bindings) != 1:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        lease = ExecutionLease(
            reservation=reservation(run), lease_id=identity.lease_id,
            lease_generation=identity.lease_generation, expires_at=identity.lease_expires_at,
        )
        if lease.reservation.result_id != identity.result_id:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        return ExecuteFacts(request=request, lease=lease)

    async def _lock_current(self, facts: ExecuteFacts) -> None:
        """Hold TASK before the CHECKERS fence; row/FK writes follow both."""
        try:
            if not await self._tasks.lock_evaluation_scope(facts.request):
                raise TrialEvidenceUnavailable("trial_evidence_unavailable")
            await ExecutionRepository(self._session).require_lease(facts.request, facts.lease)
        except CheckerExecutionUnavailable:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable") from None

    def _slot(self, subject: TrialEvidenceStableSubject) -> TrialEvidenceSlot:
        """Resolve the selected exact trusted profile; the current protocol has one plan."""
        selector = trial_selector_from_configuration(self._request.configuration)
        context = TrialAuthorityContext(
            registry_entry_id=self._request.registry.registry_entry_id,
            registry_entry_digest=self._request.registry.entry_digest,
            checker_image_digest=self._request.registry.image_digest,
            configuration_sha256=self._request.configuration_sha256,
        )
        bundle = self._profiles.read(context, selector) if selector is not None else None
        if bundle is None:
            raise TrialEvidenceUnavailable("trial_profile_unavailable")
        profile, projection = bundle
        projection.validate_profile(profile)
        identity = self._request.identity
        expected = TrialEvidenceStableSubject(
            project_id=identity.project_id, task_id=identity.task_id,
            assignment_id=identity.assignment_id, submission_id=identity.submission_id,
            submission_version=identity.submission_version,
            requirement_id=self._request.input["requirement_id"],
            registry_entry_id=self._request.registry.registry_entry_id,
            registry_entry_digest=self._request.registry.entry_digest,
            configuration_sha256=self._request.configuration_sha256,
            trial_kind=projection.trial_kind, slot_index=0,
            plan_sha256=subject.plan_sha256, input_digest=self._request.input_sha256,
            materials_digest=external_checker_json_hash([
                item.model_dump(mode="json") for item in self._request.materials
            ]),
        )
        if subject != expected or profile.selector != selector.profile or (
            projection.selector != selector.projection
        ):
            raise TrialEvidenceUnavailable("trial_subject_unavailable")
        return TrialEvidenceSlot(maximum_bytes=profile.limits.maximum_receipt_bytes)

    async def reserve(self, subject: TrialEvidenceStableSubject) -> TrialEvidenceTicket:
        """Allocate or recover one exact trial address in the caller transaction."""
        subject = TrialEvidenceStableSubject.model_validate(subject)
        facts = await self._request_facts()
        await self._authority.preflight(facts.request)
        async with self._authority.prepare_execution(facts.request) as prepared:
            await self._lock_current(facts)
            slot = self._slot(subject)
            # Immutable keys let ART retain FK/key-share custody without
            # reversing this owner's trial-row -> ART publication lock order.
            row = await self._session.scalar(select(CheckerTrialEvidence).where(
                CheckerTrialEvidence.address_digest == subject.address_digest,
            ).with_for_update(key_share=True).execution_options(populate_existing=True))
            if row is not None:
                self._match(row, subject, slot)
                # Fresh current execution authority is distinct from original provenance.
                evidence = await prepared.consume(facts)
                self._check_evidence(evidence, facts)
                return self._ticket(row, replayed=True)
            evidence = await prepared.consume(facts)
            self._check_evidence(evidence, facts)
            identity = self._request.identity
            origin = TrialEvidenceOrigin(
                checker_run_id=identity.attempt_id, worker_lease_id=identity.lease_id,
                worker_lease_generation=identity.lease_generation,
                worker_lease_expires_at=identity.lease_expires_at,
                external_request_digest=self._request.request_digest,
            )
            row = CheckerTrialEvidence(
                id=str(new_record_id()), project_id=str(subject.project_id),
                task_id=str(subject.task_id), assignment_id=str(subject.assignment_id),
                submission_id=str(subject.submission_id), submission_version=subject.submission_version,
                checker_run_id=str(origin.checker_run_id), registry_entry_id=subject.registry_entry_id,
                address_digest=subject.address_digest, subject=subject.model_dump(mode="json"),
                origin=origin.model_dump(mode="json"), maximum_bytes=slot.maximum_bytes,
                content_sha256=None, execute_evidence_id=str(evidence.evidence_id),
            )
            self._session.add(row)
            await self._session.flush()
            return self._ticket(row, replayed=False)

    async def resolve(self, selector: TrialEvidenceSelector) -> TrialEvidenceReservation:
        """Qualify exact content without mutating the pre-admission reservation."""
        selector = TrialEvidenceSelector.model_validate(selector)
        facts = await self._request_facts()
        if selector.project_id != facts.request.project_id:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        await self._lock_current(facts)
        # Pin a non-key field; FOR UPDATE would conflict with ART's FK checks.
        row = await self._session.scalar(select(CheckerTrialEvidence).where(
            CheckerTrialEvidence.id == str(selector.trial_evidence_id),
            CheckerTrialEvidence.project_id == str(facts.request.project_id),
            CheckerTrialEvidence.task_id == str(facts.request.task_id),
            CheckerTrialEvidence.assignment_id == str(facts.request.assignment_id),
            CheckerTrialEvidence.submission_id == str(facts.request.submission_id),
            CheckerTrialEvidence.submission_version == facts.request.submission_version,
        ).with_for_update(key_share=True).execution_options(populate_existing=True))
        if row is None:
            raise TrialEvidenceUnavailable("trial_evidence_unavailable")
        subject = _value(TrialEvidenceStableSubject, row.subject)
        slot = self._slot(subject)
        self._match(row, subject, slot)
        if row.content_sha256 not in {None, selector.content_sha256}:
            raise TrialEvidenceUnavailable("trial_content_conflict")
        return TrialEvidenceReservation(
            selector=selector, subject=subject, slot=slot,
            origin=_value(TrialEvidenceOrigin, row.origin),
        )

    async def pin_content(self, selector: TrialEvidenceSelector) -> TrialEvidenceReservation:
        """Retain the first hash atomically with the matching ART put admission."""
        resolved = await self.resolve(selector)
        row = await self._session.get(CheckerTrialEvidence, str(selector.trial_evidence_id))
        if row.content_sha256 is None:
            row.content_sha256 = selector.content_sha256
            await self._session.flush()
        return resolved

    @staticmethod
    def _check_evidence(evidence, facts) -> None:
        """Reject forged or wrong-phase receipts from a miscomposed authority port."""
        if type(evidence) is not ExecuteEvidence or (
            evidence.facts_digest != execution_authority_digest(facts)
        ):
            raise TrialEvidenceUnavailable("trial_authority_unavailable")

    @staticmethod
    def _match(row, subject, slot) -> None:
        """Compare all immutable facts, including hashes excluded from the address."""
        if row.address_digest != subject.address_digest or (
            _value(TrialEvidenceStableSubject, row.subject) != subject
            or row.maximum_bytes != slot.maximum_bytes
        ):
            raise TrialEvidenceUnavailable("trial_evidence_conflict")

    @staticmethod
    def _ticket(row, *, replayed: bool) -> TrialEvidenceTicket:
        """Return original provenance without treating it as current authority."""
        return TrialEvidenceTicket(
            trial_evidence_id=UUID(row.id), subject=_value(TrialEvidenceStableSubject, row.subject),
            origin=_value(TrialEvidenceOrigin, row.origin),
            slot=TrialEvidenceSlot(maximum_bytes=row.maximum_bytes),
            content_sha256=row.content_sha256, replayed=replayed,
        )
