"""Explicit composition of the shared delivery owner; feature registration is separate."""

from collections.abc import Callable, Mapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.authorization.api.outbox_dispatch import OutboxDispatchAuthorizationPort
from app.modules.outbox.api import (
    DeliveryOptions,
    FinalizedUnknownDeliveryPort,
    InvocationFencePort,
    OutboxAppendPort,
)
from app.modules.outbox.delivery import OutboxDelivery, CommittedInvocationReader
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.outbox.registry import HandlerRegistry


def outbox_invocation_fence(session: AsyncSession) -> InvocationFencePort:
    """Use the existing owner's locks in the caller's effect transaction."""
    return DeliveryRepository(session)


def finalized_unknown_deliveries(session: AsyncSession) -> FinalizedUnknownDeliveryPort:
    """Expose exact terminal UNKNOWN observation through OUTBOX's public port."""
    return DeliveryRepository(session)


def outbox_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    authorization_factory: Callable[[AsyncSession], OutboxDispatchAuthorizationPort],
    registry: HandlerRegistry,
    options: DeliveryOptions,
    event_options: Mapping[tuple[str, int], DeliveryOptions] | None = None,
) -> OutboxDelivery:
    """No default authority, installed handler, worker or runtime discovery."""
    return OutboxDelivery(
        session_factory,
        authorization_factory=authorization_factory,
        registry=registry,
        options=options,
        event_options=event_options,
    )


def production_outbox_delivery(session_factory):
    """Install exact assignment and selected evaluation handlers."""
    from app.adapters.artifacts import worker_post_submission_materialization
    from app.adapters.auth import (
        outbox_dispatch_authorization,
        assignment_invalidation_authorization,
        revision_expiry_authorization,
    )
    from app.adapters.tasks import (
        TransactionalAssignmentInvalidationHandler,
        TransactionalTaskRevisionExpiryHandler,
        TransactionalTaskRevisionExpiredNoticeHandler,
        TransactionalTaskRevisionBlockedNoticeHandler,
        evaluation_completion_handler,
        evaluation_request_handler,
    )
    from app.adapters.checkers import post_submit_delivery_reconciliation_handler
    from app.modules.checkers.api.delivery_reconciliation import (
        POST_SUBMIT_DELIVERY_RECONCILIATION_EVENT as RECONCILIATION_EVENT,
    )
    from app.modules.checkers.api.execution import COMPLETION_EVENT, REQUEST_EVENT
    from app.modules.checkers.api.external_policy import (
        SELECTED_POST_DELIVERY_LEASE_SECONDS,
        SELECTED_POST_HANDLER_TIMEOUT_SECONDS,
    )
    from app.modules.tasks.api.assignment_invalidation import ASSIGNMENT_INVALIDATION_EVENT
    from app.modules.tasks.api.revision_expiry import (
        REVISION_EXPIRY_EVENT, REVISION_EXPIRED_EVENT, REVISION_CONTEXT_BLOCKED_EVENT,
    )

    return outbox_delivery(
        session_factory,
        authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry(
            [
                (
                    ASSIGNMENT_INVALIDATION_EVENT,
                    1,
                    TransactionalAssignmentInvalidationHandler(
                        session_factory,
                        observer=CommittedInvocationReader(session_factory),
                        authorization_factory=assignment_invalidation_authorization,
                    ),
                ),
                (
                    REVISION_EXPIRY_EVENT,
                    1,
                    TransactionalTaskRevisionExpiryHandler(
                        session_factory,
                        observer=CommittedInvocationReader(session_factory),
                        authorization_factory=revision_expiry_authorization,
                    ),
                ),
                (
                    REVISION_EXPIRED_EVENT,
                    1,
                    TransactionalTaskRevisionExpiredNoticeHandler(
                        session_factory,
                        observer=CommittedInvocationReader(session_factory),
                    ),
                ),
                (
                    REVISION_CONTEXT_BLOCKED_EVENT,
                    1,
                    TransactionalTaskRevisionBlockedNoticeHandler(
                        session_factory,
                        observer=CommittedInvocationReader(session_factory),
                    ),
                ),
                (
                    REQUEST_EVENT,
                    1,
                    evaluation_request_handler(
                        sessions=session_factory,
                        materialization=worker_post_submission_materialization(
                            sessions=session_factory
                        ),
                    ),
                ),
                (
                    COMPLETION_EVENT,
                    1,
                    evaluation_completion_handler(sessions=session_factory),
                ),
                (
                    RECONCILIATION_EVENT,
                    1,
                    post_submit_delivery_reconciliation_handler(
                        sessions=session_factory,
                        materialization=worker_post_submission_materialization(
                            sessions=session_factory
                        ),
                    ),
                ),
            ],
            replay_safe=frozenset({(REVISION_EXPIRY_EVENT, 1), (REVISION_EXPIRED_EVENT, 1), (REVISION_CONTEXT_BLOCKED_EVENT, 1)}),
        ),
        options=DeliveryOptions(),
        event_options={
            (REQUEST_EVENT, 1): DeliveryOptions(
                lease_seconds=SELECTED_POST_DELIVERY_LEASE_SECONDS,
                handler_timeout_seconds=SELECTED_POST_HANDLER_TIMEOUT_SECONDS,
            )
        },
    )


def outbox_append(session: AsyncSession) -> OutboxAppendPort:
    """Compose the sole append participant behind its public transaction port."""
    from app.modules.outbox.service import OutboxService

    return OutboxService(session)


def committed_invocation_reader(sessions):
    """Expose the existing independent observer without private cross-owner imports."""
    return CommittedInvocationReader(sessions)
