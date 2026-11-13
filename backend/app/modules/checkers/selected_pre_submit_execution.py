"""One source-bound PRE invocation and independent combined-result validation."""

from __future__ import annotations

import asyncio

from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionAdapter,
    ExternalPreSubmitSourceGrant,
)
from app.interfaces.external_services import (
    ExternalServiceProtocolError,
    ExternalServiceUnavailableError,
)
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitInvocationResult,
    SelectedPreSubmitInfrastructureUnavailable,
    SelectedPreSubmitLeaseFacts,
)


class SelectedPreSubmitProcessor:
    """Run the platform defaults and selected project through one typed call."""

    def __init__(
        self, *, lease: SelectedPreSubmitLeaseFacts, execution: ExternalCheckerExecutionAdapter,
    ) -> None:
        self._lease = lease
        self._execution = execution
        self._aborted = False
        self._started = False
        self._active: asyncio.Task | None = None

    def abort(self) -> None:
        """Cancel the one invocation; runtime cleanup remains separately owned."""
        self._aborted = True
        if self._active is not None:
            self._active.cancel()

    async def process(self, grant: ExternalPreSubmitSourceGrant) -> SelectedPreSubmitInvocationResult:
        """Validate returned source, fence and derived requests before finalization."""
        if self._aborted:
            raise asyncio.CancelledError
        if self._started:
            raise SelectedPreSubmitInfrastructureUnavailable("material_unavailable")
        self._started = True
        try:
            # The source grant belongs to this foreground callback task.
            # Track it for abort without delegating source custody to a child.
            self._active = asyncio.current_task()
            result = await self._execution.execute_pre(self._lease, grant)
            if type(result) is not SelectedPreSubmitInvocationResult:
                raise ValueError("PRE result is invalid")
            result.validate_lease(self._lease)
            if (result.receipt.adapter_provider_key != self._execution.identity.provider_key
                    or result.receipt.runtime.provider != self._execution.pre_runtime_provider):
                raise ValueError("PRE provider differs")
            if result.receipt.outcome == "cancelled":
                raise asyncio.CancelledError
            return result
        except ExternalServiceUnavailableError as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("implementation_unavailable") from exc
        except (ExternalServiceProtocolError, ValueError, TypeError) as exc:
            raise SelectedPreSubmitInfrastructureUnavailable("invalid_output") from exc
        finally:
            self._active = None


__all__ = ("SelectedPreSubmitProcessor",)
