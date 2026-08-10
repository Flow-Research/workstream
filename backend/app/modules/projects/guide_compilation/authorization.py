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
        raise AuthorizationUnavailable("project guide compilation authority is unavailable")

    async def prepare_request(
        self, *, actor: ActorIdentityFacts, facts: ProjectGuideCompilationRequestFacts
    ) -> Never:
        del actor, facts
        return self._deny()

    async def consume_request(
        self,
        *,
        handle: object,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationRequestFacts,
    ) -> Never:
        del handle, actor, facts
        return self._deny()

    async def authorize_execute_preflight(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePreflightFacts,
    ) -> Never:
        del actor, facts
        return self._deny()

    async def prepare_execute_persist(
        self,
        *,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> Never:
        del actor, facts
        return self._deny()

    async def consume_execute_persist(
        self,
        *,
        handle: object,
        actor: ActorIdentityFacts,
        facts: ProjectGuideCompilationExecutePersistFacts,
    ) -> Never:
        del handle, actor, facts
        return self._deny()
