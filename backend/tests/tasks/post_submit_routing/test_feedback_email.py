"""Committed routing and Resend HTTP behavior for assignment feedback email."""

import asyncio
from datetime import timedelta
import json
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, text
from workstream_external_services import (
    ExternalServiceConfigurationError, ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)

from app.adapters import submission_feedback_email as email_adapter
from app.adapters.outbox import production_outbox_delivery
from app.adapters.tasks import task_post_submit_outcome
from app.core.config import Settings
from app.core.identifiers import new_record_id
from app.interfaces.submission_feedback_email import RESEND_PROVIDER, SubmissionFeedbackEmail
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.api import DeliveryOptions, HandlerOutcome
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.api.routing_outcome import SUBMISSION_FEEDBACK_EMAIL_EVENT
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.external.support import post_registry_spec
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.submission_dispatch.test_revision_capacity import COVERAGE_GAP


def _private_key(tmp_path):
    path = tmp_path / "resend-key"
    path.write_text("re_fake_testing_key\n", encoding="ascii")
    path.chmod(0o400)
    return path


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, payload):
        self._payload = payload

    async def __aiter__(self):
        yield self._payload


def _response(status, **body):
    return httpx.Response(status, stream=ResponseStream(json.dumps(body).encode()))


@pytest.mark.parametrize("status,body,error", [
    (200, {"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"}, None),
    (200, {"id": "not-an-id"}, ExternalServiceProtocolError),
    (409, {"name": "concurrent_idempotent_requests"}, ExternalServiceUnavailableError),
    (409, {"name": "invalid_idempotent_request"}, ExternalServiceProtocolError),
    (429, {"message": "sensitive@example.test"}, ExternalServiceUnavailableError),
    (503, {"message": "sensitive@example.test"}, ExternalServiceUnavailableError),
    (401, {}, ExternalServiceProtocolError),
    (307, {}, ExternalServiceProtocolError),
])
async def test_resend_http_mapping_and_request_privacy(tmp_path, status, body, error):
    async def server(request):
        assert str(request.url) == "https://api.resend.com/emails"
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer re_fake_testing_key"
        assert request.headers["Idempotency-Key"] == f"workstream-submission-feedback/{event_id}"
        assert json.loads(request.content) == {
            "from": "Workstream <no-reply@workstream.flowresearch.tech>",
            "to": ["verified@example.test"], "subject": "Assignment needs revision", "text": "Read feedback.",
        }
        return _response(status, **body)

    settings = Settings(environment="test", resend_api_key_file=_private_key(tmp_path))
    adapter = email_adapter.submission_feedback_email_factory(
        settings, transport=httpx.MockTransport(server),
    ).create(RESEND_PROVIDER)
    event_id = new_record_id()
    message = SubmissionFeedbackEmail(event_id, "verified@example.test", "Assignment needs revision", "Read feedback.")
    if error is None:
        await adapter.send(message)
    else:
        with pytest.raises(error) as failure:
            await adapter.send(message)
        assert "sensitive@example.test" not in str(failure.value)
        assert "re_fake_testing_key" not in str(failure.value)


def test_resend_worker_rejects_missing_or_nonprivate_key(tmp_path):
    key = _private_key(tmp_path)
    settings = Settings(environment="test", submission_feedback_email_enabled=True,
                        token_issuer="https://identity.example.test/realms/flow")
    for path in (None, tmp_path / "absent"):
        with pytest.raises(ExternalServiceConfigurationError):
            email_adapter.validate_submission_feedback_email_worker(settings.model_copy(update={"resend_api_key_file": path}))
    key.chmod(0o644)
    settings = settings.model_copy(update={"resend_api_key_file": key})
    with pytest.raises(ExternalServiceConfigurationError):
        email_adapter.validate_submission_feedback_email_worker(settings)
    key.chmod(0o400)
    email_adapter.validate_submission_feedback_email_worker(settings)
    with pytest.raises(ExternalServiceConfigurationError):
        email_adapter.validate_submission_feedback_email_worker(settings.model_copy(update={"submission_feedback_email_enabled": False}))


async def _email_events(factory):
    async with factory() as session:
        return tuple(await session.scalars(select(OutboxEvent).where(
            OutboxEvent.event_type == SUBMISSION_FEEDBACK_EMAIL_EVENT,
        )))


@pytest.mark.parametrize("case", ["retry", "unknown", "stale", "unverified", "exhausted", "coverage", "disabled"])
async def test_only_committed_current_quality_routes_send(
    tmp_path, isolated_database_env, monkeypatch, case,
):
    options = {"findings": COVERAGE_GAP, "human_review_required": False} if case == "coverage" else {}
    if case == "exhausted":
        options["max_revision_rounds"] = 0
    async with remediation_source(tmp_path, isolated_database_env, **options) as h:
        async with h.factory() as session, session.begin():
            actor_id = str(h.actor_context.actor_profile_id)
            link = await session.get(ActorIdentityLink, str(h.actor_context.identity_link_id))
            profile = await session.get(ActorProfile, actor_id)
            issuer = link.issuer
            # The signed profile test separately verifies how this state is observed.
            profile.contact_email = "exact-recipient@example.test"
            link.email_observed_issued_at = 1
            link.email_verified = case != "unverified"
        settings = h.settings.model_copy(update={
            "submission_feedback_email_enabled": case != "disabled", "token_issuer": issuer,
            "resend_api_key_file": _private_key(tmp_path),
        })
        monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
        calls = []

        async def server(request):
            calls.append((request.headers["Idempotency-Key"], json.loads(request.content)))
            if case == "retry" and len(calls) == 1:
                raise httpx.ReadTimeout("lost provider acknowledgement", request=request)
            return _response(200, id="49a3999c-0ce1-4ea6-ab68-afcd6dc2e794")

        factory = email_adapter.submission_feedback_email_factory
        monkeypatch.setattr(email_adapter, "submission_feedback_email_factory", lambda configured: factory(
            configured, transport=httpx.MockTransport(server),
        ))
        if case == "retry":
            async with h.factory() as session:
                await task_post_submit_outcome(session, h.factory).apply(h.envelope, current_generation=None)
                assert await _email_events(h.factory) == ()
                await session.rollback()
            assert await _email_events(h.factory) == ()
        async with h.factory() as session, session.begin():
            outcome = await task_post_submit_outcome(session, h.factory).apply(h.envelope, current_generation=None)
        assert outcome.routing_recommendation == "needs_revision"
        events = await _email_events(h.factory)
        if case in {"coverage", "disabled"}:
            assert events == () and calls == []
            return
        event, = events
        assert event.causation_event_id == outcome.outcome_event_id
        assert event.payload == {"routing_manifest_id": str(outcome.routing_manifest_id),
                                 "outcome": "rejected" if case == "exhausted" else "needs_revision"}
        async with h.factory() as session, session.begin():
            replay = await task_post_submit_outcome(session, h.factory).apply(h.envelope, current_generation=None)
        assert replay.replayed and [item.event_id for item in await _email_events(h.factory)] == [event.event_id]
        if case == "stale":
            async with h.factory() as session, session.begin():
                await session.execute(text(
                    "UPDATE public.workstream_tasks SET status='evaluation_pending' WHERE id=:task_id"
                ), {"task_id": h.request.task_id})
        scanner = production_outbox_delivery(h.factory)
        delivery = production_outbox_delivery(h.factory, worker_group="feedback")
        assert (SUBMISSION_FEEDBACK_EMAIL_EVENT, 1) in scanner._registry.keys
        post = production_outbox_delivery(h.factory, worker_group="post")
        assert await post.deliver(event.event_id, UUID(event.project_id), "wrong-queue", registered_only=True) is None
        assert await delivery.deliver(event.event_id, new_record_id(), "wrong-project", registered_only=True) is None
        if case in {"retry", "unknown"}:
            delivery._event_options = {
                (SUBMISSION_FEEDBACK_EMAIL_EVENT, 1): DeliveryOptions(
                    lease_seconds=6, handler_timeout_seconds=4, retry_base_seconds=1,
                ),
            }
        if case == "unknown":
            claim = await delivery.claim(event.event_id, UUID(event.project_id), "pre-crash-worker")
            envelope = await delivery._begin_invocation(claim)
            handler = delivery._registry.get(SUBMISSION_FEEDBACK_EMAIL_EVENT, 1)
            assert await handler(envelope) is HandlerOutcome.ACKNOWLEDGE
            assert len(calls) == 1
            # Commit of invocation survived the lost worker. The provider receipt did not.
            await asyncio.sleep(6.05)
            receipt = await delivery.recover(event.event_id, UUID(event.project_id))
            assert json.loads(receipt.outcome_json)["invocation_unknown"] is True
        else:
            receipt = await delivery.deliver(event.event_id, UUID(event.project_id), "email-worker", registered_only=True)
        assert receipt is not None
        if case in {"retry", "unknown"}:
            assert json.loads(receipt.outcome_json)["delivery_state"] == "retryable"
            await asyncio.sleep(1.05)
            receipt = await delivery.deliver(event.event_id, UUID(event.project_id), "email-worker", registered_only=True)
        assert json.loads(receipt.outcome_json)["delivery_state"] == "acknowledged"
        assert await delivery.deliver(event.event_id, UUID(event.project_id), "duplicate", registered_only=True) is None
        if case in {"stale", "unverified"}:
            assert calls == []
        else:
            assert len(calls) == (2 if case in {"retry", "unknown"} else 1)
            assert len(set(key for key, _ in calls)) == 1
            assert all(body == calls[0][1] for _, body in calls)
            body = calls[0][1]
            assert body["to"] == ["exact-recipient@example.test"]
            assert str(h.request.assignment_id) in body["text"]
            assert str(h.request.submission_id) not in body["text"]
            assert str(h.request.task_id) not in body["text"]
            assert ("resubmit" in body["text"]) is (case != "exhausted")


async def test_post_provider_failure_does_not_request_email(tmp_path, isolated_database_env, monkeypatch):
    class UnavailableChecker:
        async def execute(self, _request, _grant):
            raise ExternalServiceUnavailableError()

    monkeypatch.setenv("WORKSTREAM_SUBMISSION_FEEDBACK_EMAIL_ENABLED", "true")
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
    ) as h:
        await reserve(h)
        result = await live_executor(h, selected_execution=UnavailableChecker()).evaluate_post_submission(h.request)
        assert result.outcome == "infrastructure_failed"
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(result.attempt_id))
            assert run.routing_recommendation == "not_evaluated" and run.completion_event_id is None
        assert await _email_events(h.factory) == ()


async def test_expired_invocation_skips_recipient_and_resend():
    from types import SimpleNamespace
    from datetime import UTC, datetime
    from app.modules.tasks.post_submit_routing.feedback_email import (
        SUBMISSION_FEEDBACK_EMAIL_LIFETIME, TaskSubmissionFeedbackEmailHandler,
    )

    class Observer:
        async def observe_invocation(self, envelope):
            return SimpleNamespace(observed_at=envelope.occurred_at + SUBMISSION_FEEDBACK_EMAIL_LIFETIME + timedelta(seconds=1))

    def forbidden(*args, **kwargs):
        pytest.fail("expired email reached database or provider")

    owner = TaskSubmissionFeedbackEmailHandler(forbidden, observer=Observer(), recipient=forbidden, adapter=forbidden)
    envelope = SimpleNamespace(occurred_at=datetime.now(UTC), payload_json=json.dumps({
        "routing_manifest_id": str(new_record_id()), "outcome": "needs_revision",
    }))
    assert await owner(envelope) is HandlerOutcome.REJECT
