"""Explicit Resend composition and bounded email transport (ADR 0014)."""

import asyncio
import json
import os
from pathlib import Path
import re
import stat
from uuid import UUID

import httpx
from workstream_external_services import (
    ExternalServiceAdapterFactory, ExternalServiceAdapterIdentity,
    ExternalServiceConfigurationError, ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)

from app.core.config import Settings
from app.interfaces.submission_feedback_email import (
    RESEND_PROVIDER, SUBMISSION_FEEDBACK_EMAIL_CAPABILITY,
    SubmissionFeedbackEmail, SubmissionFeedbackEmailAdapter, is_single_mailbox,
)
from app.modules.outbox.api import HandlerOutcome

_IDENTITY = ExternalServiceAdapterIdentity(SUBMISSION_FEEDBACK_EMAIL_CAPABILITY, RESEND_PROVIDER)
_KEY = re.compile(rb"re_[A-Za-z0-9_-]{1,256}")
_MAX_RESPONSE_BYTES = 4096
_TIMEOUT_SECONDS = 10
_SENDER = "Workstream <no-reply@workstream.flowresearch.tech>"
_ENDPOINT = "https://api.resend.com/emails"


def _read_key(path: Path | None) -> str | None:
    """Read only a bounded regular private file owned by the worker identity."""
    if path is None or not path.is_absolute():
        return None
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o400
                    or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1
                    or not 4 <= metadata.st_size < 512):
                return None
            key = os.read(descriptor, 512).rstrip(b"\r\n")
        finally:
            os.close(descriptor)
        return key.decode("ascii") if _KEY.fullmatch(key) is not None else None
    except OSError:
        return None


class ResendSubmissionFeedbackEmailAdapter:
    """Send one plaintext message to one mailbox using Resend's idempotency key."""

    identity = _IDENTITY

    def __init__(self, key: str, transport: httpx.AsyncBaseTransport | None):
        """Keep the private key confined to this provider adapter."""
        self._key, self._transport = key, transport

    async def send(self, message: SubmissionFeedbackEmail) -> None:
        """Map only safe outcomes, keeping response content out of errors and logs."""
        if not is_single_mailbox(message.recipient):
            raise ExternalServiceProtocolError(self.identity)
        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS), httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT_SECONDS,
                trust_env=False, follow_redirects=False,
            ) as client, client.stream(
                "POST", _ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self._key}",
                    "Idempotency-Key": f"workstream-submission-feedback/{message.event_id}",
                    "Accept-Encoding": "identity",
                },
                json={"from": _SENDER, "to": [message.recipient],
                      "subject": message.subject, "text": message.text},
            ) as response:
                await _require_acceptance(response)
        except (httpx.TransportError, TimeoutError):
            raise ExternalServiceUnavailableError(self.identity) from None


async def _require_acceptance(response: httpx.Response) -> None:
    """Classify response status and inspect only bounded success or conflict data."""
    status = response.status_code
    if status in {408, 429} or status >= 500:
        raise ExternalServiceUnavailableError(_IDENTITY)
    if not (response.is_success or status == 409):
        raise ExternalServiceProtocolError(_IDENTITY)
    raw = bytearray()
    async for chunk in response.aiter_raw(chunk_size=1024):
        raw.extend(chunk)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ExternalServiceProtocolError(_IDENTITY)
    body = None
    try:
        body = json.loads(raw)
        if response.is_success and type(body) is dict and type(body.get("id")) is str:
            if str(UUID(body["id"])) == body["id"]:
                return
    except (TypeError, ValueError, RecursionError):
        pass
    if status == 409 and type(body) is dict and body.get("name") == "concurrent_idempotent_requests":
        raise ExternalServiceUnavailableError(_IDENTITY)
    raise ExternalServiceProtocolError(_IDENTITY)


def submission_feedback_email_factory(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None,
) -> ExternalServiceAdapterFactory[SubmissionFeedbackEmailAdapter]:
    """Register the one operational sender and keep key loading on its worker."""
    factory = ExternalServiceAdapterFactory[SubmissionFeedbackEmailAdapter](
        SUBMISSION_FEEDBACK_EMAIL_CAPABILITY,
    )

    def build() -> SubmissionFeedbackEmailAdapter:
        key = _read_key(settings.resend_api_key_file)
        if key is None:
            raise ExternalServiceConfigurationError(_IDENTITY)
        return ResendSubmissionFeedbackEmailAdapter(key, transport)

    factory.register(RESEND_PROVIDER, build)
    return factory


def validate_submission_feedback_email_worker(settings: Settings) -> None:
    """Require an explicitly enabled verified issuer and readable sending key at startup."""
    if (not settings.submission_feedback_email_enabled or settings.auth_provider != "flow"
            or settings.flow_auth_local_hmac_secret is not None or settings.token_issuer is None):
        raise ExternalServiceConfigurationError(_IDENTITY)
    submission_feedback_email_factory(settings).create(RESEND_PROVIDER)


def submission_feedback_email_handler(sessions, *, observer, settings: Settings):
    """Register without loading a key on the worker that discovers pending events."""
    from app.adapters.actors import verified_notification_email
    from app.adapters.auth import has_submission_feedback_recipient_grant
    from app.modules.tasks.post_submit_routing.feedback_email import TaskSubmissionFeedbackEmailHandler

    issuer = settings.token_issuer

    async def recipient(session, project_id, actor_id):
        if issuer is None or not await has_submission_feedback_recipient_grant(session, project_id, actor_id):
            return None
        return await verified_notification_email(session, actor_id, issuer)

    async def handle(envelope):
        try:
            adapter = submission_feedback_email_factory(settings).create(RESEND_PROVIDER)
        except ExternalServiceConfigurationError:
            return HandlerOutcome.REJECT
        return await TaskSubmissionFeedbackEmailHandler(
            sessions, observer=observer, recipient=recipient, adapter=adapter,
        )(envelope)

    return handle
