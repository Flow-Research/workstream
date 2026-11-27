"""Transactional contributor email capability for governed POST feedback."""

from dataclasses import dataclass, field
import re
from typing import Protocol
from uuid import UUID

from workstream_external_services import ExternalServiceAdapter

SUBMISSION_FEEDBACK_EMAIL_CAPABILITY = "submission_feedback_email"
RESEND_PROVIDER = "resend"
_LOCAL_PART = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def is_single_mailbox(value: str) -> bool:
    """Accept a single unadorned ASCII mailbox with no list or header syntax."""
    local, separator, domain = value.partition("@")
    labels = domain.split(".")
    return (len(value) <= 254 and len(local) <= 64 and bool(separator)
            and _LOCAL_PART.fullmatch(local) is not None and len(labels) >= 2
            and all(_DNS_LABEL.fullmatch(label) is not None for label in labels))


@dataclass(frozen=True, slots=True)
class SubmissionFeedbackEmail:
    """One exact event, verified recipient and bounded message."""

    event_id: UUID
    recipient: str = field(repr=False)
    subject: str
    text: str = field(repr=False)


class SubmissionFeedbackEmailAdapter(ExternalServiceAdapter, Protocol):
    """Send one email with provider idempotency supplied by its event ID."""

    async def send(self, message: SubmissionFeedbackEmail) -> None:
        """Return only after the provider acknowledges the send request."""
