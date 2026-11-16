"""Flush-only factual appends under current REV and request-local AUTH custody."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.compensation.api.fulfillment_contracts import (
    decode_fulfillment_exception, decode_fulfillment_report,
    parse_fulfillment_exception, parse_fulfillment_report,
)
from app.modules.compensation.api.fulfillment_evidence import (
    FulfillmentEvidenceAuthorizationPort, FulfillmentEvidenceDenied,
    FulfillmentEvidenceInvalid, FulfillmentEvidenceUnavailable,
    FulfillmentExceptionAcknowledgement, FulfillmentExceptionAuthorityFacts,
    FulfillmentExceptionConflict, FulfillmentReportAcknowledgement,
    FulfillmentReportAuthorityFacts, FulfillmentReportConflict,
)
from app.modules.compensation.fulfillment.models import (
    CompensationFulfillmentException, CompensationFulfillmentReceipt,
)
from app.modules.compensation.fulfillment.models import CompensationFulfillmentRoot
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.reviews.api.lifecycle import JointLifecycleCurrentCustodyPort


class FulfillmentEvidenceService:
    """Use one caller-owned root transaction; every failure requires rollback."""

    def __init__(self, session: AsyncSession, *, source_instance_id: UUID,
                 actor_profile_id: UUID, identity_link_id: UUID,
                 authorization: FulfillmentEvidenceAuthorizationPort,
                 lifecycle: JointLifecycleCurrentCustodyPort):
        self._session, self._source = session, source_instance_id
        self._actor, self._link = actor_profile_id, identity_link_id
        self._authorization, self._lifecycle = authorization, lifecycle

    async def report(self, award_id: UUID, event_id: UUID, body: bytes):
        """Append or recover exactly one full report; never repair prior evidence."""
        value = self._parse(award_id, event_id, body, exception=False)
        digest = canonical_json_hash(value)
        async with self._custody(award_id, value, digest, exception=False) as custody:
            root, existing, authority, generation = custody
            if existing is not None:
                if (existing.award_id != award_id or existing.report_body != value
                        or existing.report_digest != digest):
                    raise FulfillmentReportConflict("fulfillment_report_conflict")
                await authority.validate_replay(existing.authorization_decision_id)
                return _report_ack(existing, replay=True)
            if value["reported_status"] == "fulfilled":
                fulfilled = await self._session.scalar(select(CompensationFulfillmentReceipt.id).where(
                    CompensationFulfillmentReceipt.award_id == award_id,
                    CompensationFulfillmentReceipt.reported_status == "fulfilled",
                ))
                if fulfilled is not None:
                    raise FulfillmentReportConflict("fulfillment_report_conflict")
            decision = await authority.consume_new()
            row = CompensationFulfillmentReceipt(
                **self._row_source(root, decision, generation), id=new_record_id(),
                external_event_id=event_id, reported_status=value["reported_status"],
                report_body=value, report_digest=digest,
            )
            self._session.add(row)
            await self._session.flush()
            # The native guard assigns this single clock after all lock waits.
            # Reuse RETURNING's actual value for the independent pure decoder.
            self._decode_report(body, root.obligation_body, row.received_at)
            return _report_ack(row, replay=False)

    async def exception(self, award_id: UUID, event_id: UUID, body: bytes):
        """Retain a linked post-success incident without another economic effect."""
        value = self._parse(award_id, event_id, body, exception=True)
        digest = canonical_json_hash(value)
        async with self._custody(award_id, value, digest, exception=True) as custody:
            root, existing, authority, generation = custody
            if existing is not None:
                if (existing.award_id != award_id or existing.exception_body != value
                        or existing.exception_digest != digest):
                    raise FulfillmentExceptionConflict("fulfillment_exception_conflict")
                await authority.validate_replay(existing.authorization_decision_id)
                return _exception_ack(existing, replay=True)
            original = await self._session.scalar(select(CompensationFulfillmentReceipt).where(
                CompensationFulfillmentReceipt.fulfillment_root_id == root.id,
                CompensationFulfillmentReceipt.adapter_binding_id == root.adapter_binding_id,
                CompensationFulfillmentReceipt.external_event_id == UUID(value["original_fulfillment_event_id"]),
                CompensationFulfillmentReceipt.reported_status == "fulfilled",
            ).execution_options(populate_existing=True))
            if original is None:
                raise FulfillmentExceptionConflict("fulfillment_exception_conflict")
            decision = await authority.consume_new()
            row = CompensationFulfillmentException(
                **self._row_source(root, decision, generation), id=new_record_id(),
                exception_event_id=event_id, original_receipt_id=original.id,
                original_fulfillment_event_id=original.external_event_id,
                kind=value["kind"], exception_body=value, exception_digest=digest,
            )
            self._session.add(row)
            await self._session.flush()
            try:
                decode_fulfillment_exception(body, obligation=root.obligation_body,
                    fulfilled_report=original.report_body, received_at=row.received_at)
            except ValueError as exc:
                raise FulfillmentEvidenceInvalid("invalid_fulfillment_exception") from exc
            return _exception_ack(row, replay=False)

    @staticmethod
    def _parse(award_id, event_id, body, *, exception):
        try:
            value = (parse_fulfillment_exception(body) if exception else parse_fulfillment_report(body))
            key = "exception_event_id" if exception else "external_event_id"
            if str(award_id) != value["award_id"] or str(event_id) != value[key]:
                raise ValueError("path or idempotency identity differs")
            return value
        except ValueError as exc:
            raise FulfillmentEvidenceInvalid("invalid_fulfillment_evidence") from exc

    async def _require_transaction(self):
        if (not self._session.in_transaction() or self._session.in_nested_transaction()
                or await self._session.scalar(text("SHOW transaction_isolation")) != "read committed"):
            raise FulfillmentEvidenceUnavailable("fulfillment_evidence_requires_read_committed")

    @asynccontextmanager
    async def _custody(self, award_id, value, digest, *, exception):
        await self._require_transaction()
        locator = (await self._session.execute(select(
            CompensationFulfillmentRoot, ProjectCompensationAdapterBinding.adapter_actor_id,
        ).join(ProjectCompensationAdapterBinding,
            ProjectCompensationAdapterBinding.id == CompensationFulfillmentRoot.adapter_binding_id,
        ).where(CompensationFulfillmentRoot.award_id == award_id))).one_or_none()
        if locator is None:
            raise FulfillmentEvidenceDenied("fulfillment_evidence_unavailable")
        root, binding_actor = locator
        async with self._lifecycle.hold_current() as (current, held):
            if root.source_instance_id != self._source:
                raise FulfillmentEvidenceUnavailable("fulfillment_source_unavailable")
            await held.require_fulfillment_source(current.generation, self._source)
            existing = await self._existing(root, value, exception=exception)
            generation = existing.recording_lifecycle_generation if existing is not None else current.generation
            facts = self._facts(root, binding_actor, value, digest, generation, exception=exception)
            async with self._authorization.prepare(facts) as authority:
                await self._lock_source(root, held, current.generation)
                yield root, existing, authority, generation

    async def _existing(self, root, value, *, exception):
        model = CompensationFulfillmentException if exception else CompensationFulfillmentReceipt
        event = model.exception_event_id if exception else model.external_event_id
        key = "exception_event_id" if exception else "external_event_id"
        return await self._session.scalar(select(model).where(
            model.adapter_binding_id == root.adapter_binding_id, event == UUID(value[key]),
        ).execution_options(populate_existing=True))

    async def _lock_source(self, root, held, generation):
        binding = await self._session.scalar(select(ProjectCompensationAdapterBinding).where(
            ProjectCompensationAdapterBinding.id == root.adapter_binding_id,
        ).with_for_update().execution_options(populate_existing=True))
        refreshed = await self._session.scalar(select(CompensationFulfillmentRoot).where(
            CompensationFulfillmentRoot.id == root.id,
        ).with_for_update().execution_options(populate_existing=True))
        if (binding is None or refreshed is None or binding.adapter_actor_id != str(self._actor)
                or binding.project_id != root.project_id
                or await self._session.scalar(text(
                    "SELECT public.compensation_fulfillment_root_is_valid(r) "
                    "FROM public.compensation_fulfillment_roots r WHERE r.id=:id"
                ), {"id": root.id}) is not True):
            raise FulfillmentEvidenceUnavailable("fulfillment_source_unavailable")
        # This held view validates custody without taking REV again after AUTH.
        await held.require_fulfillment_source(generation, self._source)

    def _facts(self, root, binding_actor, value, digest, generation, *, exception):
        common = dict(source_instance_id=root.source_instance_id, fulfillment_root_id=root.id,
            award_id=root.award_id, project_id=UUID(root.project_id),
            adapter_binding_id=root.adapter_binding_id, binding_actor_id=UUID(binding_actor),
            reporter_actor_id=self._actor, reporter_identity_link_id=self._link,
            source_award_digest=root.source_award_digest, obligation_digest=root.obligation_digest,
            admission_generation=root.admission_generation, recording_lifecycle_generation=generation)
        if exception:
            return FulfillmentExceptionAuthorityFacts(**common,
                exception_event_id=UUID(value["exception_event_id"]), exception_digest=digest,
                original_fulfillment_event_id=UUID(value["original_fulfillment_event_id"]))
        return FulfillmentReportAuthorityFacts(**common,
            external_event_id=UUID(value["external_event_id"]), report_digest=digest)

    def _row_source(self, root, decision, generation):
        return dict(fulfillment_root_id=root.id, award_id=root.award_id, project_id=root.project_id,
            source_instance_id=root.source_instance_id, adapter_binding_id=root.adapter_binding_id,
            reporter_actor_id=str(self._actor), reporter_identity_link_id=str(self._link),
            authorization_decision_id=decision.authorization_decision_id,
            authorization_resource_digest=decision.resource_context_digest,
            recording_lifecycle_generation=generation)

    @staticmethod
    def _decode_report(body, obligation, received_at):
        try:
            decode_fulfillment_report(body, obligation=obligation, received_at=received_at)
        except ValueError as exc:
            raise FulfillmentEvidenceInvalid("invalid_fulfillment_report") from exc


def _report_ack(row, *, replay):
    return FulfillmentReportAcknowledgement(receipt_id=row.id, award_id=row.award_id,
        fulfillment_root_id=row.fulfillment_root_id, external_event_id=row.external_event_id,
        report_digest=row.report_digest, replay=replay)


def _exception_ack(row, *, replay):
    return FulfillmentExceptionAcknowledgement(exception_id=row.id, award_id=row.award_id,
        fulfillment_root_id=row.fulfillment_root_id, exception_event_id=row.exception_event_id,
        original_fulfillment_event_id=row.original_fulfillment_event_id,
        exception_digest=row.exception_digest, replay=replay)
