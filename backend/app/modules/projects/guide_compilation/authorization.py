"""Deny-only composition seam for inactive guide compilation authority."""

from __future__ import annotations

from typing import Never

from app.modules.authorization.api import (
    ActorIdentityFacts,
    AuthorizationUnavailable,
    ProjectGuideCompilationExecutePersistFacts,
    ProjectGuideCompilationExecutePreflightFacts,
    ProjectGuideCompilationRequestFacts,
)


class DenyProjectGuideCompilationAuthorization:
    """Keep every compilation boundary unavailable until AUTH-12I."""

    @staticmethod
    def _deny() -> Never:
        """Raise the stable unavailable-authority denial."""
        raise AuthorizationUnavailable("project guide compilation authority is unavailable")

    async def prepare_request(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationRequestFacts
    ) -> Never:
        """Deny request preparation before AUTH activates the action."""
        del actor, facts
        return self._deny()

    async def consume_request(
        self,
        *,
        handle: object,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
    ) -> Never:
        """Deny request consumption without inspecting an alleged handle."""
        del handle, actor, facts
        return self._deny()

    async def authorize_execute_preflight(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
    ) -> Never:
        """Deny fixed-service execution preflight while unavailable."""
        del actor, facts
        return self._deny()

    async def prepare_execute_persist(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> Never:
        """Deny accepted-result persistence preparation while unavailable."""
        del actor, facts
        return self._deny()

    async def consume_execute_persist(
        self,
        *,
        handle: object,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> Never:
        """Deny persistence consumption without touching product state."""
        del handle, actor, facts
        return self._deny()
