"""Flush-only persistence and bounded reads for ContributionPolicy behavior."""

import hashlib
from uuid import UUID

from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.modules.contributions.api import ContributionPolicyProjectSelection

from app.modules.contributions.models import (
    ContributionAwardDefinition,
    ContributionPolicy,
    ContributionPolicyLifecycleEvent,
    ContributionPolicyTransitionCustody,
    ContributionPolicyVersion,
    ContributionRule,
    ProjectCompensationUnit,
)


def policy_operation_lock_key(operation_id: UUID) -> int:
    """Derive a stable signed advisory key from an operation UUID."""
    raw = int.from_bytes(hashlib.sha256(operation_id.bytes).digest()[:8], "big")
    return raw - (1 << 64) if raw >= (1 << 63) else raw


class ContributionPolicyRepository:
    """Persist policy behavior inside the caller-owned root transaction."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind persistence to the caller-owned session and transaction."""
        self._session = session

    async def current_policy_candidates(self, project_id: UUID) -> list[UUID]:
        """Select IDs only, without locks; a second candidate means ambiguity."""
        return list(await self._session.scalars(select(ContributionPolicy.id).where(
            ContributionPolicy.project_id == str(project_id),
            ContributionPolicy.status != "retired",
        ).limit(2)))

    async def current_policy_selection(
        self, project_id: UUID, policy_id: UUID,
    ) -> ContributionPolicyProjectSelection | None:
        """Read one post-authorization snapshot; never switch selected aggregates."""
        candidate_count = select(func.count()).select_from(ContributionPolicy).where(
            ContributionPolicy.project_id == str(project_id),
            ContributionPolicy.status != "retired",
        ).correlate(None).scalar_subquery()
        rows = (await self._session.execute(select(
            ContributionPolicy.id, ContributionPolicy.current_published_version_id,
            ContributionPolicyVersion.id.label("open_draft_version_id"),
        ).outerjoin(ContributionPolicyVersion, and_(
            ContributionPolicyVersion.contribution_policy_id == ContributionPolicy.id,
            ContributionPolicyVersion.project_id == ContributionPolicy.project_id,
            ContributionPolicyVersion.status == "draft",
        )).where(
            ContributionPolicy.project_id == str(project_id),
            ContributionPolicy.id == policy_id, ContributionPolicy.status != "retired",
            candidate_count == 1,
        ).limit(2))).all()
        if len(rows) != 1:
            return None
        row = rows[0]
        if row.current_published_version_id is None and row.open_draft_version_id is None:
            return None
        return ContributionPolicyProjectSelection(
            project_id=project_id, contribution_policy_id=row.id,
            current_published_version_id=row.current_published_version_id,
            open_draft_version_id=row.open_draft_version_id,
        )

    async def lock_operation(self, operation_id: UUID) -> None:
        """Serialize requests sharing one immutable operation identifier."""
        await self._session.execute(
            text("select pg_advisory_xact_lock(:key)"),
            {"key": policy_operation_lock_key(operation_id)},
        )

    async def lock_project_scope(self, project_id: UUID) -> None:
        """Serialize policy creation within one project scope."""
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"contribution-policy:{project_id}"},
        )

    async def get_event_by_operation(
        self, operation_id: UUID
    ) -> ContributionPolicyLifecycleEvent | None:
        """Load immutable recovery evidence for one operation."""
        return await self._session.scalar(
            select(ContributionPolicyLifecycleEvent).where(
                ContributionPolicyLifecycleEvent.operation_id == operation_id
            )
        )

    async def get_policy(
        self, project_id: UUID, policy_id: UUID, *, for_update: bool = False
    ) -> ContributionPolicy | None:
        """Load an exact same-project policy, optionally retaining its row lock."""
        query = select(ContributionPolicy).where(
            ContributionPolicy.project_id == str(project_id),
            ContributionPolicy.id == policy_id,
        )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def get_reusable_policy(self, project_id: UUID) -> ContributionPolicy | None:
        """Lock the newest non-retired policy aggregate for draft creation."""
        return await self._session.scalar(
            select(ContributionPolicy)
            .where(
                ContributionPolicy.project_id == str(project_id),
                ContributionPolicy.status != "retired",
            )
            .order_by(ContributionPolicy.created_at.desc())
            .limit(1)
            .with_for_update()
        )

    async def get_open_draft(self, project_id: UUID) -> ContributionPolicyVersion | None:
        """Lock any open draft version for the exact project."""
        return await self._session.scalar(
            select(ContributionPolicyVersion)
            .where(
                ContributionPolicyVersion.project_id == str(project_id),
                ContributionPolicyVersion.status == "draft",
            )
            .limit(1)
            .with_for_update()
        )

    async def next_version_number(self, policy_id: UUID) -> int:
        """Return the next monotonic version number for a policy aggregate."""
        current = await self._session.scalar(
            select(func.max(ContributionPolicyVersion.version_number)).where(
                ContributionPolicyVersion.contribution_policy_id == policy_id
            )
        )
        return int(current or 0) + 1

    async def get_version(
        self,
        project_id: UUID,
        policy_id: UUID,
        version_id: UUID,
        *,
        for_update: bool = False,
        graph: bool = False,
    ) -> ContributionPolicyVersion | None:
        """Load an exact policy version with optional graph and row custody."""
        query = select(ContributionPolicyVersion).where(
            ContributionPolicyVersion.project_id == str(project_id),
            ContributionPolicyVersion.contribution_policy_id == policy_id,
            ContributionPolicyVersion.id == version_id,
        )
        if graph:
            query = query.options(
                selectinload(ContributionPolicyVersion.rules).selectinload(
                    ContributionRule.award_definitions
                )
            )
        if for_update:
            query = query.with_for_update()
        return await self._session.scalar(query.execution_options(populate_existing=True))

    async def get_selected_version(
        self,
        policy: ContributionPolicy,
        version_id: UUID | None,
    ) -> ContributionPolicyVersion | None:
        """Resolve an explicit or current version with its immutable graph."""
        selected = version_id or policy.current_published_version_id
        if selected is None:
            return await self._session.scalar(
                select(ContributionPolicyVersion)
                .where(
                    ContributionPolicyVersion.project_id == policy.project_id,
                    ContributionPolicyVersion.contribution_policy_id == policy.id,
                )
                .order_by(ContributionPolicyVersion.version_number.desc())
                .limit(1)
                .options(
                    selectinload(ContributionPolicyVersion.rules).selectinload(
                        ContributionRule.award_definitions
                    )
                )
            )
        return await self.get_version(UUID(policy.project_id), policy.id, selected, graph=True)

    async def lock_unit(
        self, project_id: UUID, instrument_type: str, unit_code: str
    ) -> ProjectCompensationUnit | None:
        """Lock one exact project-owned compensation unit."""
        return await self._session.scalar(
            select(ProjectCompensationUnit)
            .where(
                ProjectCompensationUnit.project_id == str(project_id),
                ProjectCompensationUnit.instrument_type == instrument_type,
                ProjectCompensationUnit.unit_code == unit_code,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_publication_graph(
        self, version_id: UUID
    ) -> tuple[list[ContributionRule], list[ContributionAwardDefinition]]:
        """Lock and refresh an exact version graph in canonical publication order."""
        rules = list(
            (
                await self._session.scalars(
                    select(ContributionRule)
                    .where(ContributionRule.contribution_policy_version_id == version_id)
                    .order_by(ContributionRule.contribution_type, ContributionRule.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        definitions = list(
            (
                await self._session.scalars(
                    select(ContributionAwardDefinition)
                    .where(ContributionAwardDefinition.contribution_policy_version_id == version_id)
                    .order_by(
                        ContributionAwardDefinition.instrument_type,
                        ContributionAwardDefinition.unit_code,
                        ContributionAwardDefinition.adapter_binding_id,
                        ContributionAwardDefinition.id,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        by_rule: dict[UUID, list[ContributionAwardDefinition]] = {rule.id: [] for rule in rules}
        for definition in definitions:
            by_rule[definition.contribution_rule_id].append(definition)
        for rule in rules:
            set_committed_value(rule, "award_definitions", by_rule[rule.id])
        return rules, definitions

    async def create_transition_custody(self, custody: ContributionPolicyTransitionCustody) -> None:
        """Flush custody first and load its database-owned transition time."""
        self._session.add(custody)
        await self._session.flush()
        await self._session.refresh(custody)

    async def flush_transition_event(self, event: ContributionPolicyLifecycleEvent) -> None:
        """Flush one protected lifecycle transition and its immutable event."""
        await self._session.flush()
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)

    async def add_policy_version_event(
        self,
        policy: ContributionPolicy,
        version: ContributionPolicyVersion,
        event: ContributionPolicyLifecycleEvent,
    ) -> None:
        """Flush a new policy, version, and lifecycle event atomically."""
        self._session.add_all((policy, version))
        await self._session.flush()
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)

    async def replace_graph(
        self,
        version: ContributionPolicyVersion,
        rules: list[ContributionRule],
        definitions: list[ContributionAwardDefinition],
        event: ContributionPolicyLifecycleEvent,
    ) -> None:
        """Replace the complete draft graph and append its lifecycle event."""
        rule_ids = select(ContributionRule.id).where(
            ContributionRule.contribution_policy_version_id == version.id
        )
        await self._session.execute(
            delete(ContributionAwardDefinition).where(
                ContributionAwardDefinition.contribution_rule_id.in_(rule_ids)
            )
        )
        await self._session.execute(
            delete(ContributionRule).where(
                ContributionRule.contribution_policy_version_id == version.id
            )
        )
        self._session.add_all([*rules, *definitions])
        await self._session.flush()
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
