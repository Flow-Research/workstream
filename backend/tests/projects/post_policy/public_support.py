"""Public approval and captured broker delivery with real SQL and AUTH owners."""

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest

from app.core.config import get_settings
from app.modules.projects.api.post_policy import post_policy_task_id
from tests.projects.guide_compilation.proposals.pg_support import proposal_case
from tests.projects.guide_compilation.proposals.public_support import proposal_client, proposal_path


@pytest.fixture
def post_policy_worker(monkeypatch):
    """Configure only an isolated broker and forbid inference/evaluation entry points."""
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
    from app.modules.artifacts.guide_document_access import ScopedGuideDocumentGrant

    monkeypatch.setenv("WORKSTREAM_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("WORKSTREAM_CELERY_RESULT_BACKEND_URL", "cache+memory://")
    get_settings.cache_clear()
    from app.workers import post_policy

    async def forbidden(*args, **kwargs):
        pytest.fail("policy setup accessed inference or a submitted-work evaluator")
    monkeypatch.setattr(OpenAIAgentSdkProjectGuideRuntime, "compile_project_guide", forbidden)
    monkeypatch.setattr(ScopedGuideDocumentGrant, "open", forbidden)
    yield post_policy
    get_settings.cache_clear()


@asynccontextmanager
async def public_approved_case(url, monkeypatch, *, broker_failure=False):
    """Commit the actual public approval; capture only its broker publication."""
    from app.modules.projects.post_policy import queue

    published = []
    def enqueue(approval_id):
        published.append(approval_id)
        if broker_failure:
            raise OSError("isolated broker unavailable")
    monkeypatch.setattr(queue, "enqueue_derivation", enqueue)
    async with proposal_case(url) as (_, factory, command, actor, grant):
        async with proposal_client(factory, actor) as client:
            path = proposal_path(command)
            package = await client.get(path + "/proposal")
            assert package.status_code == 200, package.text
            assert package.json()["post_submit_policy_id"] is None
            result = await client.post(path + "/pre-submission-approval",
                headers={"Idempotency-Key": str(uuid4())},
                json={"target": package.json()["target"],
                      "acknowledged_warning_hashes": package.json()["warning_hashes"]})
            assert result.status_code == 200, result.text
            approval_id = UUID(result.json()["operation_id"])
            assert published == [approval_id]
        yield factory, command, actor, grant, approval_id, published


def deliver(worker, approval_id):
    """Execute the actual Celery task with its canonical broker identity."""
    return worker.derive_post_policy.apply(
        args=(str(approval_id),), task_id=str(post_policy_task_id(approval_id)), throw=True,
    ).get()
