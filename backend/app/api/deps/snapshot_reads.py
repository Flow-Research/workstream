"""The one REPEATABLE READ response transaction the contributor and project management reads share.

Each response starts one snapshot, records the AUTH decision in it, reads the
owner rows, validates the response, then commits the decision evidence. The
caller names its cursor refusal, its owner faults and their responses; AUTH
denials are never caught here, so the decision owner restages and conceals
them.
"""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_controls import StructuredHTTPException


async def start_read_snapshot(session: AsyncSession) -> None:
    """Start the one REPEATABLE READ snapshot that every statement of this response reads."""
    if session.in_transaction():
        await session.commit()
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


async def run_snapshot_read(
    session: AsyncSession,
    authorize: Callable[[], Awaitable[object]],
    read,
    *,
    cursor_invalid: type[Exception],
    invalid_cursor: Callable[[], StructuredHTTPException],
    faults: tuple[type[Exception], ...],
    unavailable: Callable[[], StructuredHTTPException],
    in_snapshot: bool = False,
):
    """Authorize, read and validate in one snapshot; roll back and map a refused cursor or owner fault."""
    try:
        if not in_snapshot:
            await start_read_snapshot(session)
        grant = await authorize()
        response = await read(grant)
        response.model_dump(mode="json")
        await session.commit()
        return response
    except cursor_invalid as exc:
        await session.rollback()
        raise invalid_cursor() from exc
    except faults as exc:
        await session.rollback()
        raise unavailable() from exc
