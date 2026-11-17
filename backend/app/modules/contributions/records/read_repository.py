"""Fixed-membership contribution selection and canonical rule projection."""

from datetime import datetime, timedelta
import math
from uuid import UUID

from sqlalchemy import and_, or_, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import new_record_id
from app.db.errors import integrity_constraint_name
from app.modules.contributions.api.source_reads import ContributionTaskSourceReadPort, ContributionTaskSourceFacts
from app.modules.contributions.api.records import (
    MAX_EXPORT_MEMBERS, ContributionExportAtCapacity, ContributionExportTooLarge,
    ContributionExportUnavailable, ContributionReadRequest, InvalidContributionCursor,
)
from app.modules.contributions.models import (
    ContributionAwardDefinition, ContributionPolicyVersion, ContributionRule,
)
from app.modules.contributions.records.models import ContributionExportSnapshot, ContributionRecord
from app.modules.contributions.records.pagination import (
    ContributionExportCursorCodec, contribution_export_query_digest,
)
from app.modules.contributions.records.read_facts import (
    ContributionReadFacts, ContributionReadPage, FrozenContributionAward,
)

_SLOT_CONSTRAINT = "uq_contribution_export_snapshots_actor_slot"
_MAX_SLOTS = 5
_PRUNE_BATCH = 25


def _slot_conflict(error: IntegrityError) -> bool:
    """Classify only the actor/slot uniqueness fence, never other SQL failures."""
    original = error.orig
    return (
        getattr(original, "sqlstate", None) == "23505"
        and integrity_constraint_name(error) == _SLOT_CONSTRAINT
    )


class ContributionReadRepository:
    """Read immutable evidence in the caller's authorized repeatable-read transaction."""

    def __init__(self, session: AsyncSession, *, cursor_codec: ContributionExportCursorCodec, tasks: ContributionTaskSourceReadPort) -> None:
        """Use the response transaction for membership, snapshot and evidence reads."""
        self._session = session
        self._cursor_codec = cursor_codec
        self._tasks = tasks

    async def read(self, request: ContributionReadRequest) -> ContributionReadPage:
        """Prune bounded expired state and return one exact initial/retained page."""
        request = ContributionReadRequest.model_validate(request)
        await self._prune_expired(request.actor_profile_id)
        digest = contribution_export_query_digest(request)
        if request.cursor is None:
            return await self._first_page(request, digest)
        return await self._continuation(request, digest)

    @staticmethod
    def _filtered(query, request: ContributionReadRequest):
        """Apply the authorized audience and canonical request filters to a query."""
        if request.audience == "self":
            query = query.where(ContributionRecord.contributor_id == str(request.actor_profile_id))
        if request.project_id is not None:
            query = query.where(ContributionRecord.project_id == str(request.project_id))
        if request.contribution_type is not None:
            query = query.where(ContributionRecord.contribution_type == request.contribution_type)
        if request.recorded_from is not None:
            query = query.where(ContributionRecord.created_at >= request.recorded_from)
        if request.recorded_before is not None:
            query = query.where(ContributionRecord.created_at < request.recorded_before)
        return query

    async def _first_page(self, request: ContributionReadRequest, digest: str) -> ContributionReadPage:
        """Select bounded membership and retain it only when continuation is required."""
        selected = self._filtered(select(ContributionRecord.id), request).order_by(
            ContributionRecord.created_at, ContributionRecord.id,
        ).limit(MAX_EXPORT_MEMBERS + 1)
        member_ids = tuple((await self._session.scalars(selected)).all())
        if len(member_ids) > MAX_EXPORT_MEMBERS:
            raise ContributionExportTooLarge("Contribution export exceeds 100000 records; narrow the filters")
        if len(set(member_ids)) != len(member_ids):
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        page_ids = member_ids[:request.limit]
        next_cursor = None
        if len(member_ids) > request.limit:
            snapshot = await self._allocate_snapshot(request.actor_profile_id, digest, member_ids)
            next_cursor = self._cursor_codec.encode(
                query_digest=digest, snapshot_id=snapshot.id, next_offset=len(page_ids),
                expires_at=snapshot.expires_at,
            )
        return ContributionReadPage(await self._load_records(request, page_ids), next_cursor)

    async def _continuation(
        self, request: ContributionReadRequest, digest: str,
    ) -> ContributionReadPage:
        """Load the next slice solely from the verified retained membership."""
        assert request.cursor is not None
        position = self._cursor_codec.decode(request.cursor, query_digest=digest)
        snapshot = await self._session.get(ContributionExportSnapshot, position.snapshot_id)
        if (
            snapshot is None or snapshot.actor_profile_id != str(request.actor_profile_id)
            or snapshot.query_digest != digest or snapshot.expires_at != position.expires_at
        ):
            raise InvalidContributionCursor("invalid contribution cursor")
        now = await self._session.scalar(select(func.clock_timestamp()))
        members = tuple(snapshot.member_ids)
        if (
            now is None or snapshot.expires_at <= now or position.expires_at <= now
            or not 2 <= len(members) <= MAX_EXPORT_MEMBERS
            or len(set(members)) != len(members)
            or position.next_offset >= len(members)
        ):
            raise InvalidContributionCursor("invalid contribution cursor")
        page_ids = members[position.next_offset:position.next_offset + request.limit]
        next_offset = position.next_offset + len(page_ids)
        next_cursor = (
            self._cursor_codec.encode(
                query_digest=digest, snapshot_id=snapshot.id, next_offset=next_offset,
                expires_at=snapshot.expires_at,
            ) if next_offset < len(members) else None
        )
        return ContributionReadPage(await self._load_records(request, page_ids), next_cursor)

    async def _allocate_snapshot(
        self, actor_profile_id: UUID, digest: str, member_ids: tuple[UUID, ...],
    ) -> ContributionExportSnapshot:
        """Claim one actor-local slot and persist immutable membership for one hour."""
        now = await self._session.scalar(select(func.clock_timestamp()))
        assert now is not None
        occupied = (await self._session.execute(select(
            ContributionExportSnapshot.allocation_slot, ContributionExportSnapshot.expires_at,
        ).where(ContributionExportSnapshot.actor_profile_id == str(actor_profile_id)))).all()
        occupied_slots = {slot for slot, _ in occupied}
        free_slot = next((slot for slot in range(1, _MAX_SLOTS + 1)
                          if slot not in occupied_slots), None)
        if free_slot is None:
            earliest = min(expiry for _, expiry in occupied)
            retry_after = max(1, min(3600, math.ceil((earliest - now).total_seconds())))
            raise ContributionExportAtCapacity(retry_after)
        snapshot = ContributionExportSnapshot(
            id=new_record_id(), actor_profile_id=str(actor_profile_id),
            allocation_slot=free_slot, query_digest=digest, member_ids=list(member_ids),
            created_at=now, expires_at=now + timedelta(hours=1),
        )
        self._session.add(snapshot)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            if _slot_conflict(exc):
                # The competing row may be invisible to this RR snapshot.
                # The outer response owner rolls this entire attempt back.
                raise ContributionExportAtCapacity(3600) from exc
            raise
        return snapshot

    async def _prune_expired(self, actor_profile_id: UUID) -> None:
        """Delete at most 25 expired ephemeral rows, preferring caller slot reuse."""
        now = await self._session.scalar(select(func.clock_timestamp()))
        assert now is not None
        removed = await self._delete_expired(
            limit=_MAX_SLOTS, actor_profile_id=actor_profile_id, now=now,
        )
        remaining = _PRUNE_BATCH - removed
        if remaining:
            await self._delete_expired(limit=remaining, actor_profile_id=None, now=now)

    async def _delete_expired(
        self, *, limit: int, actor_profile_id: UUID | None, now: datetime,
    ) -> int:
        """Delete a bounded expired set with skip-locked contention handling."""
        ids = select(ContributionExportSnapshot.id).where(
            ContributionExportSnapshot.expires_at <= now,
        )
        if actor_profile_id is not None:
            ids = ids.where(ContributionExportSnapshot.actor_profile_id == str(actor_profile_id))
        ids = ids.order_by(
            ContributionExportSnapshot.expires_at, ContributionExportSnapshot.id,
        ).limit(limit).with_for_update(skip_locked=True)
        deleted = await self._session.scalars(delete(ContributionExportSnapshot).where(
            ContributionExportSnapshot.id.in_(ids),
        ).returning(ContributionExportSnapshot.id))
        return len(deleted.all())

    async def _load_records(
        self, request: ContributionReadRequest, ids: tuple[UUID, ...],
    ) -> tuple[ContributionReadFacts, ...]:
        """Load exact records and frozen rule terms in retained membership order."""
        if not ids:
            return ()
        query = select(
            ContributionRecord, ContributionPolicyVersion.version_number,
            ContributionRule.id, ContributionRule.compensation_mode,
        ).outerjoin(
            ContributionPolicyVersion,
            and_(ContributionPolicyVersion.id == ContributionRecord.contribution_policy_version_id,
                 ContributionPolicyVersion.project_id == ContributionRecord.project_id),
        ).outerjoin(ContributionRule, and_(
            ContributionRule.contribution_policy_version_id == ContributionRecord.contribution_policy_version_id,
            ContributionRule.project_id == ContributionRecord.project_id,
            ContributionRule.contribution_type == ContributionRecord.contribution_type,
        )).where(ContributionRecord.id.in_(ids))
        query = self._filtered(query, request).order_by(ContributionRecord.created_at, ContributionRecord.id)
        rows = (await self._session.execute(query)).all()
        if tuple(row.id for row, _, _, _ in rows) != ids:
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        if any(version is None or rule is None or mode is None for _, version, rule, mode in rows):
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        selectors = {(UUID(row.project_id),UUID(row.task_id),UUID(row.submission_id)) for row,_,_,_ in rows}
        sources = {}
        for item in await self._tasks.read_contribution_tasks(tuple(selectors)):
            item = ContributionTaskSourceFacts.model_validate(item)
            key = (item.project_id,item.task_id,item.submission_id)
            if key not in selectors or key in sources:
                raise ContributionExportUnavailable("Contribution evidence unavailable")
            sources[key] = item
        if set(sources) != selectors:
            raise ContributionExportUnavailable("Contribution evidence unavailable")
        reviewer_rules = {rule for row,_,rule,_ in rows if row.contribution_type == "completed_review"}
        selected_ids = {source.contribution_award_definition_id for source in sources.values()
                        if source.contribution_award_definition_id is not None}
        definitions = (await self._session.scalars(select(ContributionAwardDefinition).where(or_(
            ContributionAwardDefinition.id.in_(selected_ids),
            ContributionAwardDefinition.contribution_rule_id.in_(reviewer_rules),
        )))).all()
        result = []
        for row, version, rule, mode in rows:
            source = sources[(UUID(row.project_id),UUID(row.task_id),UUID(row.submission_id))]
            submitter = row.contribution_type == "accepted_submission"
            if submitter and source.contribution_policy_version_id != row.contribution_policy_version_id:
                raise ContributionExportUnavailable("Contribution evidence unavailable")
            exact = tuple(FrozenContributionAward(
                id=d.id, instrument=d.instrument_type, unit=d.unit_code, quantity=d.quantity,
            ) for d in definitions if d.contribution_rule_id == rule and (
                not submitter or (d.id == source.contribution_award_definition_id and d.task_size == source.task_size)
            ))
            result.append(self._facts(row, version, mode, exact, source.task_size if submitter else None))
        return tuple(result)

    @staticmethod
    def _facts(row, version, mode, definitions, task_size) -> ContributionReadFacts:
        """Validate the exact stored source shape without deriving recognition."""
        return ContributionReadFacts(
            id=row.id, project_id=UUID(row.project_id), task_id=UUID(row.task_id),
            submission_id=UUID(row.submission_id), contribution_type=row.contribution_type,
            contributor_id=UUID(row.contributor_id), source_review_id=row.source_review_id,
            source_review_lease_id=row.source_review_lease_id,
            source_final_acceptance_id=row.source_final_acceptance_id,
            source_task_assignment_id=(None if row.source_task_assignment_id is None
                                       else UUID(row.source_task_assignment_id)),
            artifact_hash=row.artifact_hash,
            contribution_policy_version_id=row.contribution_policy_version_id,
            recorded_at=row.created_at, policy_version_number=version,
            compensation_mode=mode, award_definitions=definitions, task_size=task_size,
        )
