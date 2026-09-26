"""Compose retained history owners and canonical AUTH in one read transaction."""

import base64
import binascii
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import get_authorization_service, get_authorization_actor_identity
from app.core.api_controls import StructuredHTTPException
from app.core.hashing import canonical_json_hash
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.adapters.auth import history_read_authorization
from app.modules.tasks.api.submission_history import HistoryReadAuthorityFacts, HistoryReadAuthorityPort
from app.adapters.tasks import submission_history_repository
from app.modules.tasks.api.submission_history import ContributorSubmissionHistoryPage, ManagementSubmissionHistoryPage
from app.adapters.checkers import checker_history_repository
from app.modules.checkers.api.history import ContributorCheckerHistoryPage, ManagementCheckerHistoryPage


class _HistoryCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: str
    actor_id: UUID
    project_id: UUID
    parent_id: UUID
    limit: int = Field(ge=1, le=100)
    position_id: UUID
    version: int | None = Field(default=None, ge=1, strict=True)
    created_at: datetime | None = None

    @model_validator(mode="after")
    def exact_position(self):
        if (self.version is None) == (self.created_at is None):
            raise ValueError("invalid history position")
        if self.created_at is not None and self.created_at.utcoffset() is None:
            raise ValueError("naive history position")
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate cursor field")
        result[key] = value
    return result


def _decode(cursor, *, action, actor_id, parent_id, project_id, limit, submission_page):
    if cursor is None:
        return None
    try:
        if len(cursor) > 1024:
            raise ValueError("oversized cursor")
        raw = base64.b64decode(cursor, altchars=b"-_", validate=True)
        value = _HistoryCursor.model_validate(json.loads(raw, object_pairs_hook=_unique_object))
        if (
            value.action != action or value.actor_id != actor_id or value.parent_id != parent_id
            or value.limit != limit or (project_id is not None and value.project_id != project_id)
            or submission_page != (value.version is not None)
        ):
            raise ValueError("cursor scope differs")
        return value
    except (ValueError, TypeError, binascii.Error) as exc:
        raise HTTPException(422, "Invalid history cursor") from exc


def _encode(*, action, actor_id, target, parent_id, limit, last, submission_page):
    value = _HistoryCursor(
        action=action, actor_id=actor_id, project_id=target.project_id, parent_id=parent_id,
        limit=limit, position_id=last.id,
        version=last.version if submission_page else None,
        created_at=None if submission_page else last.created_at,
    )
    return base64.urlsafe_b64encode(value.model_dump_json().encode()).decode()


def _missing():
    return StructuredHTTPException(status_code=404, detail="Project authorization resource not found",
        error_code="project_authorization_resource_not_found", error_message="Project authorization resource not found")


class HistoryReadOperation:
    """Resolve exact ownership, lock TASK then AUTH, validate projection then commit."""

    def __init__(self, session, actor_id, authority: HistoryReadAuthorityPort, submissions, checkers):
        self._session, self._actor_id, self._authority = session, actor_id, authority
        self._submissions, self._checkers = submissions, checkers

    async def _resolve_checker_owner(self, run_id, *, project_id, contributor_id):
        reference = await self._checkers.resolve_run_reference(run_id)
        if reference is None:
            return None
        target = await self._submissions.resolve_submission(
            reference.submission_id, project_id=project_id, contributor_id=contributor_id,
        )
        return target if target is not None and target.task_id == reference.task_id else None

    async def read(
        self, kind: Literal["submissions", "submission", "checker_runs", "checker_run"],
        resource_id: UUID, *, project_id: UUID | None = None, limit: int = 25, cursor: str | None = None,
    ):
        manager = project_id is not None
        action = ("project." if manager else "") + {
            "submissions": "task.submission.list", "submission": "submission.read",
            "checker_runs": "submission.checker_run.list", "checker_run": "checker_run.read",
        }[kind]
        submission_page = kind == "submissions"
        after = _decode(cursor, action=action, actor_id=self._actor_id, parent_id=resource_id,
                        project_id=project_id, limit=limit, submission_page=submission_page)
        selectors = {"project_id": project_id, "contributor_id": None if manager else self._actor_id}
        resolve = (
            self._submissions.resolve_task_history if kind == "submissions" else
            self._resolve_checker_owner if kind == "checker_run" else self._submissions.resolve_submission
        )
        try:
            target = await resolve(resource_id, **selectors)
            if target is None:
                raise _missing()
            if after is not None and after.project_id != target.project_id:
                raise HTTPException(422, "Invalid history cursor")
            if not await self._submissions.lock_history_task(target):
                raise _missing()
            if await resolve(resource_id, **selectors) != target:
                raise _missing()
            await self._authority.require_history(HistoryReadAuthorityFacts(
                action=action, resource_type=(
                    "task_submission_history" if kind == "submissions" else
                    "checker_history" if kind == "checker_run" else "submission_history"
                ), resource_id=resource_id, target=target, actor_id=self._actor_id,
                query_digest=canonical_json_hash({"action": action, "limit": limit, "cursor": cursor}),
            ))
            position = None if after is None else (
                after.version if submission_page else after.created_at, after.position_id,
            )
            if kind in {"submission", "submissions"}:
                items, more = await self._submissions.read(
                    target, manager=manager, submission_id=resource_id if kind == "submission" else None,
                    limit=limit, after=position,
                )
                page_type = ManagementSubmissionHistoryPage if manager else ContributorSubmissionHistoryPage
            else:
                items, more = await self._checkers.read(
                    submission_id=target.submission_id, task_id=target.task_id, manager=manager, run_id=resource_id if kind == "checker_run" else None,
                    limit=limit, after=position,
                )
                page_type = ManagementCheckerHistoryPage if manager else ContributorCheckerHistoryPage
            if kind in {"submission", "checker_run"}:
                if len(items) != 1:
                    raise _missing()
                response = items[0]
            else:
                next_cursor = _encode(
                    action=action, actor_id=self._actor_id, target=target, parent_id=resource_id,
                    limit=limit, last=items[-1], submission_page=submission_page,
                ) if more else None
                response = page_type(items=items, next_cursor=next_cursor)
            response.model_dump(mode="json")
            await self._session.commit()
            return response
        except (ValueError, SQLAlchemyError) as exc:
            await self._session.rollback()
            raise StructuredHTTPException(
                status_code=503, detail="History unavailable", error_code="history_unavailable",
                error_message="History unavailable", retryable=True,
            ) from exc


async def get_history_reads(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    actor: Annotated[ActorIdentityFacts, Depends(get_authorization_actor_identity)],
    authority: Annotated[object, Depends(get_authorization_service)],
):
    submissions = submission_history_repository(session)
    return HistoryReadOperation(
        session, actor.actor_profile_id, history_read_authorization(authority),
        submissions, checker_history_repository(session),
    )
