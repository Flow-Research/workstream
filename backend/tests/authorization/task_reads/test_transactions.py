"""Real prepared decisions remain atomic with their detached read response."""

import pytest
from pydantic import TypeAdapter
from sqlalchemy import func, select

from app.adapters.audit import task_transition_audit
from app.adapters.tasks import task_commands
from app.core.config import get_settings
from app.db import session as db_session
from app.modules.audit.service import AuditService
from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable
from app.modules.authorization.task_authorization import PreparedTaskAuthorization
from app.modules.tasks.models import AuditEvent
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService
from tests.authorization.task_authority.test_postgresql import context
from tests.authorization.task_queues.support import grant_queue_role
from tests.authorization.task_reads.support import READS, task_case


async def count(session, actor, action):
    return await session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id == str(actor), AuditEvent.action_id == action))


@pytest.mark.parametrize("kind", READS)
async def test_task_read_rollback(admin_access, monkeypatch, kind):
    project, manager, task = await task_case(admin_access)
    await grant_queue_role(admin_access, project, "submitter" if kind.startswith("contributor") else "project_manager")
    actor = await context(admin_access)
    factory = db_session.get_session_factory()
    action = READS[kind][1]
    for failure in ("projection", "serialization", "validation", "audit"):
        staged = []
        async with factory() as session:
            authority = PreparedTaskAuthorization(session, actor)
            commands = task_commands(session, settings=get_settings(), authorization=authority,
                audit=task_transition_audit(session), actor_profile_id=actor.actor_profile_id)
            original = authority.consume
            async def observe(handle, facts):
                result = await original(handle, facts)
                assert await count(session, actor.actor_profile_id, action) == 1
                async with factory() as other:
                    assert await count(other, actor.actor_profile_id, action) == 0
                staged.append(result.decision_id)
                return result
            with monkeypatch.context() as patch:
                patch.setattr(authority, "consume", observe)
                async def broken(*args, **kwargs):
                    raise RuntimeError("read projection failure")
                def invalid(*args, **kwargs):
                    raise RuntimeError("read response failure")
                if failure == "projection":
                    owner = TaskService if kind.endswith("requirements") else TaskRepository
                    method = "_load_locked_task_context" if kind.endswith("requirements") else "read_" + kind.replace("_detail", "_task_detail")
                    patch.setattr(owner, method, broken)
                elif failure in {"serialization", "validation"}:
                    patch.setattr(TypeAdapter, "dump_json" if failure == "serialization" else "validate_json", invalid)
                else:
                    async def unavailable(*args, **kwargs):
                        raise AuthorizationEvidenceUnavailable("audit unavailable")
                    patch.setattr(AuditService, "add_authority_event", unavailable)
                with pytest.raises(AuthorizationEvidenceUnavailable if failure == "audit" else RuntimeError):
                    await getattr(commands, kind)(*((project, task) if kind.startswith("management") else (task,)))
            assert bool(staged) is (failure != "audit")
            assert not session.in_transaction()
        async with factory() as independent:
            assert await count(independent, actor.actor_profile_id, action) == 0
