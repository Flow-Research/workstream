"""Compose the caller's own grant and work reads with canonical AUTH in one read transaction."""

from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from typing import Literal

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import get_authorization_actor_identity, get_authorization_service
from app.api.deps.snapshot_reads import run_snapshot_read, start_read_snapshot
from app.core.api_controls import StructuredHTTPException
from app.db.session import get_db_session
from app.modules.artifacts.api.submission_command import (
    AssignmentIntakeAttempt, AssignmentIntakeQuery, AssignmentIntakeReadPort, AssignmentIntakeUnavailable,
)
from app.modules.artifacts.api.submission_preparation import (
    SubmissionBundlePreparationDetail, SubmissionBundlePreparationPage, SubmissionBundlePreparationReadPort,
    SubmissionBundlePreparationSummary,
)
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.authorization.api.contributor_reads import (
    ActorProjectRoles, ContributorReadAuthorizationPort, ContributorReadCursorInvalid, ContributorReadPosition,
    ContributorReadRequest, ContributorReadUnavailable,
)
from app.modules.checkers.api.execution import CheckerExecutionUnavailable
from app.modules.checkers.api.history import CheckerHistoryReadPort, ContributorCheckerResult
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitUnavailable
from app.modules.contributions.api.records import AcceptedAssignmentEvidence, AcceptedAssignmentEvidencePort
from app.modules.compensation.api.award_reads import ContributorAwardTotal, ContributorAwardTotalsPort
from app.modules.projects.api.guide_documents import GuideDocumentUnavailable
from app.modules.projects.api.guide_reads import (
    ApprovedContributorGuide, ProjectGuideDocumentContentPort, ProjectGuideReadPort, ProjectGuideReadUnavailable,
)
from app.modules.projects.api.project_summaries import ProjectStatus, ProjectSummaryFacts, ProjectSummaryReadPort
from app.modules.tasks.api.contributor_reads import (
    AssignmentState, ContributorAssignment, ContributorAssignmentCounts, ContributorAssignmentPage,
    ContributorAssignmentQuery, TaskStatus,
    ContributorSubmissionCounts, ContributorSubmissionPage, ContributorSubmissionQuery, ContributorWorkCounts,
    ContributorWorkReadPort,
)
from app.modules.tasks.api.submission_history import SubmissionAttemptStatus


_FROZEN = ConfigDict(extra="forbid", frozen=True)
AdminRoleName = Literal["access_administrator", "operator", "project_manager", "finance_authority", "audit_authority"]


class ActiveGuide(BaseModel):
    """The project's currently active guide identity."""
    model_config = _FROZEN
    guide_id: UUID
    version: str


class ActorProject(BaseModel):
    """A project where the caller holds an exact grant, with the caller's effective roles."""

    model_config = _FROZEN
    project_id: UUID
    name: str
    status: ProjectStatus
    admin_roles: tuple[AdminRoleName, ...]
    project_roles: tuple[Literal["submitter", "reviewer"], ...]
    active_guide: ActiveGuide | None

    @classmethod
    def from_facts(cls, facts: ProjectSummaryFacts, roles: ActorProjectRoles) -> "ActorProject":
        """Join one project's facts with the caller's roles on it."""
        guide = facts.active_guide
        return cls(
            project_id=facts.project_id, name=facts.name, status=facts.status,
            admin_roles=roles.admin_roles, project_roles=roles.project_roles,
            active_guide=None if guide is None else ActiveGuide(guide_id=guide.guide_id, version=guide.version),
        )


class ActorProjectPage(BaseModel):
    """One page of the caller's exact-grant projects."""
    model_config = _FROZEN
    items: tuple[ActorProject, ...]
    next_cursor: str | None


class AwardTotal(BaseModel):
    """The exact sum of the caller's immutable awards; not a payment or fulfillment claim."""

    model_config = _FROZEN
    instrument: Literal["money", "project_points"]
    unit: str
    quantity: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$")


class ContributorWorkSummary(BaseModel):
    """The caller's own work counts and award totals in their Submitter projects."""
    model_config = _FROZEN
    project_id: UUID | None
    assignments: ContributorAssignmentCounts
    submissions: ContributorSubmissionCounts
    award_totals: tuple[AwardTotal, ...]

    @classmethod
    def from_facts(cls, project_id, counts: ContributorWorkCounts, totals) -> "ContributorWorkSummary":
        """Build the summary from TASK counts and compensation totals."""
        return cls(
            project_id=project_id, assignments=counts.assignments, submissions=counts.submissions,
            award_totals=tuple(
                AwardTotal(instrument=total.instrument_type, unit=total.unit_code, quantity=format(total.quantity, "f"))
                for total in totals
            ),
        )


def _missing() -> StructuredHTTPException:
    """The concealed not-found response shared by every contributor read."""
    return StructuredHTTPException(
        status_code=404, detail="Project authorization resource not found",
        error_code="project_authorization_resource_not_found",
        error_message="Project authorization resource not found",
    )


def _cursor_invalid() -> StructuredHTTPException:
    """A malformed, forged or substituted continuation."""
    return StructuredHTTPException(
        status_code=422, detail="Invalid contributor read cursor",
        error_code="contributor_read_cursor_invalid", error_message="Invalid contributor read cursor",
    )


def _unavailable() -> StructuredHTTPException:
    """The retryable failure for any infrastructure or integrity fault."""
    return StructuredHTTPException(
        status_code=503, detail="Contributor read unavailable",
        error_code="contributor_read_unavailable", error_message="Contributor read unavailable",
        retryable=True,
    )


def _instant(value: datetime | None) -> str | None:
    """Canonical cursor-bound text for an optional instant."""
    return None if value is None else value.astimezone(UTC).isoformat(timespec="microseconds")


def _id(value: UUID | None) -> str | None:
    """Canonical cursor-bound text for an optional identifier."""
    return None if value is None else str(value)


class ExactContributorAssignment(BaseModel):
    """Current status, retained intake and governed evidence for one owned claim."""

    model_config = _FROZEN
    assignment: ContributorAssignment
    current_status: TaskStatus | Literal["closed", "rejected"]
    status_reason: str | None
    next_action: Literal["submit", "awaiting_intake", "awaiting_evaluation", "revise", "wait_for_processing", "none"]
    intake: AssignmentIntakeAttempt | None
    feedback_submission_id: UUID | None
    post_submission_results: tuple[ContributorCheckerResult, ...] = Field(max_length=100)
    next_cursor: str | None
    accepted_evidence: AcceptedAssignmentEvidence | None


class ContributorReadOperation:
    """Authorize first, project only the caller's rows, validate, then commit evidence."""

    def __init__(
        self, session: AsyncSession, actor_id: UUID, authority: ContributorReadAuthorizationPort, *,
        work: ContributorWorkReadPort, preparations: SubmissionBundlePreparationReadPort,
        projects: ProjectSummaryReadPort, awards: ContributorAwardTotalsPort,
        guides: ProjectGuideReadPort, guide_documents: ProjectGuideDocumentContentPort,
        intake: AssignmentIntakeReadPort, checker_history: CheckerHistoryReadPort,
        accepted_evidence: AcceptedAssignmentEvidencePort,
    ) -> None:
        """Compose the AUTH decision port and the owner read ports for one request."""
        self._session, self._actor_id, self._authority = session, actor_id, authority
        self._work, self._preparations = work, preparations
        self._projects, self._awards = projects, awards
        self._guides, self._guide_documents = guides, guide_documents
        self._intake, self._checker_history, self._accepted_evidence = intake, checker_history, accepted_evidence

    async def _run(self, request: ContributorReadRequest, read, *, in_snapshot: bool = False):
        """One bounded read: AUTH denials propagate to the decision owner for restaging."""
        return await run_snapshot_read(
            self._session, lambda: self._authority.authorize(request), read,
            cursor_invalid=ContributorReadCursorInvalid, invalid_cursor=_cursor_invalid,
            faults=(ContributorReadUnavailable, SelectedPreSubmitUnavailable, SQLAlchemyError,
                    ProjectGuideReadUnavailable, GuideDocumentUnavailable, AssignmentIntakeUnavailable,
                    CheckerExecutionUnavailable, ValueError),
            unavailable=_unavailable, in_snapshot=in_snapshot,
        )

    def _request(self, action, query, *, cursor=None, resource_id=None, project_id=None):
        """Bind the action, actor, scope and canonical filters into one AUTH request."""
        return ContributorReadRequest(
            action=action, actor_profile_id=self._actor_id, resource_id=resource_id or self._actor_id,
            scope_project_id=project_id, query=tuple(sorted(query.items())), presented_cursor=cursor,
        )

    def _next(self, request, more, last_timestamp, last_id) -> str | None:
        """Sign the last row's position only when another page exists."""
        return self._authority.encode(request, ContributorReadPosition(last_timestamp, last_id)) if more else None

    async def projects(self, *, limit: int, cursor: str | None):
        """A1: projects where the caller holds an exact admin or contributor grant."""
        request = self._request("actor.project.list", {"limit": limit, "order": "created_at_id_asc"}, cursor=cursor)

        async def read(grant):
            after = None if grant.position is None else (grant.position.timestamp, grant.position.record_id)
            rows, more = await self._projects.read_project_summaries(grant.project_ids, after=after, limit=limit)
            roles = await self._authority.project_roles(self._actor_id, tuple(row.project_id for row in rows))
            items = tuple(ActorProject.from_facts(row, roles[row.project_id]) for row in rows)
            last: ProjectSummaryFacts | None = rows[-1] if rows else None
            return ActorProjectPage(items=items, next_cursor=self._next(
                request, more, last.created_at if last else None, last.project_id if last else None,
            ))

        return await self._run(request, read)

    async def approved_guide(self, project_id: UUID) -> ApprovedContributorGuide:
        request = self._request(
            "project.contributor_guide.read", {}, resource_id=project_id, project_id=project_id,
        )

        async def read(_grant):
            selected = await self._guides.read_approved_contributor_guide(project_id)
            if selected is None:
                await self._session.commit()
                raise _missing()
            return selected.guide

        return await self._run(request, read)

    @asynccontextmanager
    async def approved_guide_document(self, project_id: UUID, guide_id: UUID, document_id: UUID):
        request = self._request(
            "project.contributor_guide.read", {"guide_id": str(guide_id), "document_id": str(document_id)},
            resource_id=project_id, project_id=project_id,
        )
        async with AsyncExitStack() as stack:
            verified = None

            async def read(_grant):
                selected = await self._guides.read_approved_contributor_guide(project_id)
                if selected is not None and selected.guide.guide_id == guide_id:
                    for original, document in zip(selected.originals, selected.guide.documents, strict=True):
                        if document.document_id == document_id:
                            nonlocal verified
                            verified = await stack.enter_async_context(self._guide_documents.open(project_id, original))
                            return document
                await self._session.commit()
                raise _missing()

            await self._run(request, read)
            yield verified

    async def assignment(self, assignment_id: UUID, *, limit: int, cursor: str | None):
        """Resolve only an exact owned assignment before project read authorization."""
        try:
            await start_read_snapshot(self._session)
            project_id = await self._work.resolve_own_assignment_project(assignment_id, self._actor_id)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise _unavailable() from exc
        if project_id is None:
            await self._session.rollback()
            raise _missing()
        request = self._request(
            "task.assignment.read", {"limit": limit},
            resource_id=assignment_id, project_id=project_id, cursor=cursor,
        )

        async def read(grant):
            selected = await self._work.read_own_assignment(project_id, assignment_id, self._actor_id)
            if selected is None:
                await self._session.commit()
                raise _missing()
            assignment = selected.assignment
            task_id = assignment.task_id
            intake = await self._intake.read_assignment_attempt(AssignmentIntakeQuery(
                project_id, task_id, assignment_id, self._actor_id, selected.active_operation_id,
            ))
            latest = assignment.latest_submission
            history = None if latest is None else await self._checker_history.read_current_attempt(
                submission_id=latest.submission_id, task_id=task_id,
            )
            results, after = self._assignment_feedback(history, grant.position, limit, request)
            status, reason, action = self._assignment_status(assignment, intake, history)
            evidence = None
            if status == "accepted" and latest is not None and latest.status == "accepted":
                evidence = await self._accepted_evidence.read_accepted_assignment(
                    project_id=project_id, task_id=task_id, assignment_id=assignment_id,
                    contributor_id=self._actor_id, submission_id=latest.submission_id,
                )
                if evidence is None:
                    raise ValueError("accepted assignment evidence is unavailable")
            return ExactContributorAssignment(
                assignment=assignment, current_status=status, status_reason=reason, next_action=action,
                intake=intake, feedback_submission_id=history.submission_id if history is not None else None,
                post_submission_results=results, next_cursor=after, accepted_evidence=evidence,
            )

        return await self._run(request, read, in_snapshot=True)

    def _assignment_feedback(self, history, position, limit, request):
        if history is None:
            if position is not None:
                raise ContributorReadCursorInvalid("assignment feedback changed")
            return (), None
        stamp = history.completed_at or history.created_at
        start = 0
        if position is not None:
            if stamp != position.timestamp:
                raise ContributorReadCursorInvalid("assignment feedback changed")
            for index, finding in enumerate(history.results):
                if finding.id == position.record_id:
                    start = index + 1
                    break
            else:
                raise ContributorReadCursorInvalid("assignment feedback changed")
        page = tuple(history.results[start:start + limit])
        more = start + limit < len(history.results)
        return page, self._next(request, more, stamp, page[-1].id if page else None)

    @staticmethod
    def _assignment_status(assignment, intake, history):
        latest = assignment.latest_submission
        if assignment.state == "closed":
            if assignment.assignment_status == "revision_expired":
                return "rejected", "revision_deadline_expired", "none"
            if assignment.assignment_status == "revision_exhausted":
                return "rejected", "revision_limit_reached", "none"
            if assignment.assignment_status == "authority_revoked":
                return "closed", "authority_revoked", "none"
            if latest is not None and latest.status in {"accepted", "rejected"}:
                return latest.status, latest.status_reason, "none"
            return "closed", assignment.assignment_status, "none"

        status = assignment.task_status
        if status is None:
            raise ValueError("active assignment is missing its task state")
        if intake is not None and intake.stage in {"receiving", "pre_checking"}:
            return status, "submission_in_progress", "awaiting_intake"
        if (intake is not None and intake.operationally_stalled
                or status == "evaluation_pending" and history is not None and history.status == "infrastructure_failed"):
            return status, "processing_unavailable", "wait_for_processing"
        if status in {"submitted", "evaluation_pending", "review_pending"}:
            return status, None, "awaiting_evaluation"
        reason = intake.failure_code if intake is not None else None
        if reason is None and status == "needs_revision" and assignment.revision is not None:
            reason = (latest.status_reason if latest is not None else None) if assignment.revision.disposition == "ready" else assignment.revision.disposition
        action = "submit" if assignment.next_action == "prepare_submission" else assignment.next_action
        return status, reason, action

    async def assignments(self, *, project_id, state: AssignmentState | None, updated_since, limit, cursor):
        request = self._request("actor.assignment.list", {
            "limit": limit, "order": "activity_at_id_asc", "state": state,
            "updated_since": _instant(updated_since),
        }, cursor=cursor, project_id=project_id)

        async def read(grant):
            items, more = await self._work.read_assignments(ContributorAssignmentQuery(
                contributor_id=self._actor_id, project_ids=grant.project_ids, state=state,
                updated_since=updated_since, limit=limit,
                after=None if grant.position is None else (grant.position.timestamp, grant.position.record_id),
            ))
            return ContributorAssignmentPage(items=items, next_cursor=self._next(
                request, more, items[-1].updated_at if items else None, items[-1].assignment_id if items else None,
            ))

        return await self._run(request, read)

    async def submissions(
        self, *, project_id, task_id, status: SubmissionAttemptStatus | None, updated_since, limit, cursor,
    ):
        request = self._request("actor.submission.list", {
            "limit": limit, "order": "activity_at_id_asc", "status": status, "task_id": _id(task_id),
            "updated_since": _instant(updated_since),
        }, cursor=cursor, project_id=project_id)

        async def read(grant):
            items, more = await self._work.read_submissions(ContributorSubmissionQuery(
                contributor_id=self._actor_id, project_ids=grant.project_ids, task_id=task_id, status=status,
                updated_since=updated_since, limit=limit,
                after=None if grant.position is None else (grant.position.timestamp, grant.position.record_id),
            ))
            return ContributorSubmissionPage(items=items, next_cursor=self._next(
                request, more, items[-1].updated_at if items else None, items[-1].submission_id if items else None,
            ))

        return await self._run(request, read)

    async def summary(self, *, project_id):
        request = self._request("actor.work_summary.read", {}, project_id=project_id)

        async def read(grant):
            counts: ContributorWorkCounts = await self._work.count_work(self._actor_id, grant.project_ids)
            totals: tuple[ContributorAwardTotal, ...] = await self._awards.read_award_totals(
                self._actor_id, grant.project_ids,
            )
            return ContributorWorkSummary.from_facts(project_id, counts, totals)

        return await self._run(request, read)

    async def _task_project(self, task_id: UUID) -> UUID:
        """Resolve the task inside the response snapshot that the authorized read then uses."""
        try:
            await start_read_snapshot(self._session)
            project_id = await self._work.resolve_contributor_task(task_id, self._actor_id)
        except SQLAlchemyError as exc:
            await self._session.rollback()
            raise _unavailable() from exc
        if project_id is None:
            await self._session.rollback()
            raise _missing()
        return project_id

    async def preparations(self, *, task_id: UUID, limit: int, cursor: str | None):
        project_id = await self._task_project(task_id)
        request = self._request("task.submission_bundle_preparation.list", {
            "limit": limit, "order": "created_at_id_desc",
        }, cursor=cursor, resource_id=task_id, project_id=project_id)

        async def read(grant):
            items, more = await self._preparations.read(
                actor_profile_id=self._actor_id, task_id=task_id, preparation_id=None, limit=limit,
                before=None if grant.position is None else (grant.position.timestamp, grant.position.record_id),
            )
            summaries = tuple(
                SubmissionBundlePreparationSummary(**item.model_dump(exclude={"findings"})) for item in items
            )
            return SubmissionBundlePreparationPage(items=summaries, next_cursor=self._next(
                request, more, items[-1].created_at if items else None, items[-1].preparation_id if items else None,
            ))

        return await self._run(request, read, in_snapshot=True)

    async def preparation(self, *, task_id: UUID, preparation_id: UUID) -> SubmissionBundlePreparationDetail:
        project_id = await self._task_project(task_id)
        request = self._request(
            "task.submission_bundle_preparation.read", {"task_id": str(task_id)},
            resource_id=preparation_id, project_id=project_id,
        )

        async def read(grant):
            items, _ = await self._preparations.read(
                actor_profile_id=self._actor_id, task_id=task_id, preparation_id=preparation_id,
                limit=1, before=None,
            )
            if len(items) != 1:
                await self._session.commit()
                raise _missing()
            return items[0]

        return await self._run(request, read, in_snapshot=True)


async def get_contributor_reads(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[ActorIdentityFacts, Depends(get_authorization_actor_identity)],
    authority: Annotated[object, Depends(get_authorization_service)],
) -> ContributorReadOperation:
    """Build the contributor read operation from request-scoped owner adapters."""
    from app.adapters.artifacts import (
        project_guide_documents_port, submission_bundle_preparation_reader, submission_operation_read_service,
    )
    from app.adapters.auth import contributor_read_authorization
    from app.adapters.checkers import checker_history_repository
    from app.adapters.compensation import contributor_award_totals_port
    from app.adapters.contributions import accepted_assignment_evidence_reader
    from app.adapters.projects import project_guide_reader, project_summary_reader
    from app.adapters.tasks import contributor_work_reader

    return ContributorReadOperation(
        session, actor.actor_profile_id,
        contributor_read_authorization(authority, session, request.app.state.settings.pagination_cursor_hmac_secret),
        work=contributor_work_reader(session), preparations=submission_bundle_preparation_reader(session),
        projects=project_summary_reader(session), awards=contributor_award_totals_port(session),
        guides=project_guide_reader(session), guide_documents=project_guide_documents_port(session, request.app.state.settings),
        intake=submission_operation_read_service(session, None), checker_history=checker_history_repository(session),
        accepted_evidence=accepted_assignment_evidence_reader(session),
    )
