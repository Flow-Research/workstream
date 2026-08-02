"""Authorized guide-bound review and revision policy mutation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.actors.service import ResolvedActor
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    MatchedAuthorityKind,
    PreparedAuthorizationInput,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectReviewPolicyMutationResourceContext,
    ProjectRevisionPolicyMutationResourceContext,
    ProjectPolicyMutationPrepareDenialResourceContext,
    authorization_resource_digest,
)
from app.modules.projects.models import ProjectGuide, ReviewPolicy, RevisionPolicy
from app.modules.projects.policy_lineage import (
    ReviewPolicySemantics,
    RevisionPolicySemantics,
    policy_digest,
)
from app.modules.projects.policy_mutation_replay_repository import (
    PolicyMutationReplayRepository,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    ReviewPolicyInput,
    ReviewPolicyResponse,
    RevisionPolicyInput,
    RevisionPolicyResponse,
)
from app.modules.projects.service import GuideEditBlocked, GuideNotFound, ProjectServiceError


NO_CURRENT_POLICY_ETAG = '"no-current-policy"'


def policy_selector_etag(policy_id: str, generation: int, policy_hash: str) -> str:
    """Return the exact opaque HTTP entity tag for one selected policy version."""
    return f'"{policy_id}.{generation}.{policy_hash.removeprefix("sha256:")}"'


class PolicyMutationConflict(ProjectServiceError):
    """The optimistic selector or replay record no longer matches."""

    status_code = 409


@dataclass(frozen=True, slots=True)
class PolicyMutationOutcome:
    """One transaction-owned policy mutation result."""

    response: ReviewPolicyResponse | RevisionPolicyResponse
    replayed: bool


class ProjectPolicyMutationService:
    """Sole authorized writer for immutable guide policy versions."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind product and replay repositories to one transaction."""
        self._projects = ProjectRepository(session)
        self._replay = PolicyMutationReplayRepository(session)

    @staticmethod
    def _if_match_value(if_match: str) -> tuple[UUID, int, str] | None:
        """Parse an exact initial sentinel or canonical policy selector."""
        if if_match == NO_CURRENT_POLICY_ETAG:
            return None
        if len(if_match) > 2 and if_match[0] == if_match[-1] == '"':
            parts = if_match[1:-1].split(".")
            if (
                len(parts) == 3
                and len(parts[2]) == 64
                and all(character in "0123456789abcdef" for character in parts[2])
            ):
                try:
                    generation = int(parts[1])
                    if generation < 1 or parts[1] != str(generation):
                        raise ValueError
                    return UUID(parts[0]), generation, f"sha256:{parts[2]}"
                except ValueError:
                    pass
        raise PolicyMutationConflict("policy_precondition_invalid")

    @staticmethod
    def _prove(decision, project_id: UUID) -> None:
        """Require exact Project Manager authority proof."""
        if (
            decision.matched_authority_kind is not MatchedAuthorityKind.ADMIN_ROLE_GRANT
            or decision.matched_grant_id is None
            or decision.matched_scope_project_id not in {None, project_id}
        ):
            raise RuntimeError("policy mutation lacked Project Manager authority")

    @staticmethod
    def _guide_selector(
        kind: Literal["review", "revision"], guide: ProjectGuide
    ) -> tuple[UUID, int, str] | None:
        """Read the exact selected policy tuple from one guide."""
        policy_id = getattr(guide, f"selected_{kind}_policy_id")
        generation = getattr(guide, f"selected_{kind}_policy_generation")
        digest = getattr(guide, f"selected_{kind}_policy_hash")
        if policy_id is None:
            return None
        return UUID(policy_id), generation, digest

    @staticmethod
    def _resource(
        *,
        kind: Literal["review", "revision"],
        policy_id: UUID,
        operation_id: UUID,
        request_digest: str,
        project_id: UUID,
        guide_id: UUID,
        guide_version: str,
        generation: int,
        final_digest: str,
        predecessor_id: UUID | None,
        predecessor_generation: int | None,
        predecessor_digest: str | None,
    ) -> ProjectReviewPolicyMutationResourceContext | ProjectRevisionPolicyMutationResourceContext:
        """Compose the exact final PREP resource facts."""
        values = {
            "resource_type": f"project_{kind}_policy_mutation",
            "resource_id": policy_id,
            "operation_id": operation_id,
            "request_digest": request_digest,
            "scope_project_id": project_id,
            "guide_id": guide_id,
            "guide_version": guide_version,
            "guide_status": "draft",
            f"{kind}_policy_id": policy_id,
            "policy_generation": generation,
            "policy_digest": final_digest,
            "predecessor_policy_id": predecessor_id,
            "predecessor_policy_generation": predecessor_generation,
            "current_policy_digest": predecessor_digest,
        }
        return (
            ProjectReviewPolicyMutationResourceContext(**values)
            if kind == "review"
            else ProjectRevisionPolicyMutationResourceContext(**values)
        )

    async def _existing(self, resolved, action, key, digest, project_id, guide_id, response_type):
        """Return an exact committed replay or reject unsafe reuse."""
        record = await self._replay.find(resolved.profile.id, action.value, key)
        if record is None:
            return None
        if (
            record.project_id != str(project_id)
            or record.guide_id != str(guide_id)
            or record.request_digest != digest
        ):
            raise PolicyMutationConflict("idempotency_mismatch")
        if record.status != "committed" or record.response_json is None:
            raise PolicyMutationConflict("idempotency_pending")
        response = response_type.model_validate(record.response_json)
        if response.policy_hash != record.policy_hash:
            raise RuntimeError("committed policy replay lost digest custody")
        return PolicyMutationOutcome(response, True)

    async def replace_review_policy(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        if_match: str,
        project_id: UUID,
        guide_id: UUID,
        payload: ReviewPolicyInput,
    ) -> PolicyMutationOutcome:
        """Authorize, append, and select one review-policy version."""
        semantics = ReviewPolicySemantics.model_validate(payload.model_dump())
        return await self._replace(
            "review",
            resolved,
            prepared,
            key,
            if_match,
            project_id,
            guide_id,
            semantics,
            ReviewPolicyResponse,
        )

    async def replace_revision_policy(
        self,
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        if_match: str,
        project_id: UUID,
        guide_id: UUID,
        payload: RevisionPolicyInput,
    ) -> PolicyMutationOutcome:
        """Authorize, append, and select one revision-policy version."""
        semantics = RevisionPolicySemantics.model_validate(payload.model_dump())
        return await self._replace(
            "revision",
            resolved,
            prepared,
            key,
            if_match,
            project_id,
            guide_id,
            semantics,
            RevisionPolicyResponse,
        )

    async def _replace(
        self,
        kind: Literal["review", "revision"],
        resolved: ResolvedActor,
        prepared: PreparedAuthorizationService,
        key: UUID,
        if_match: str,
        project_id: UUID,
        guide_id: UUID,
        semantics: ReviewPolicySemantics | RevisionPolicySemantics,
        response_type,
    ) -> PolicyMutationOutcome:
        """Execute the shared exact policy mutation transaction."""
        expected_selector = self._if_match_value(if_match)
        action = (
            ActionId.PROJECT_REVIEW_POLICY_UPDATE
            if kind == "review"
            else ActionId.PROJECT_REVISION_POLICY_UPDATE
        )
        policy_id, operation_id = uuid4(), uuid4()
        semantic_values = semantics.model_dump(mode="json")
        final_digest = policy_digest(kind, semantics)
        predecessor_id = expected_selector[0] if expected_selector is not None else None
        predecessor_generation = expected_selector[1] if expected_selector is not None else None
        predecessor_digest = expected_selector[2] if expected_selector is not None else None
        generation = 1 if expected_selector is None else predecessor_generation + 1
        request_digest = canonical_json_hash(
            {
                "domain": "workstream.policy_mutation.idempotency.v1",
                "method": "PUT",
                "action_id": action.value,
                "project_id": str(project_id),
                "guide_id": str(guide_id),
                "policy_kind": kind,
                "if_match": if_match,
                "semantics": semantic_values,
                "idempotency_key": str(key),
            }
        )
        existing = await self._existing(
            resolved, action, key, request_digest, project_id, guide_id, response_type
        )
        if existing is not None:
            return existing
        guide_snapshot = await self._projects.get_guide(str(guide_id))
        if guide_snapshot is None or guide_snapshot.project_id != str(project_id):
            raise GuideNotFound("guide not found")
        if guide_snapshot.status != "draft":
            raise GuideEditBlocked("only draft guides can change policy")
        snapshot_selector = self._guide_selector(kind, guide_snapshot)
        if snapshot_selector != expected_selector:
            raise PolicyMutationConflict("policy_precondition_failed")
        resource = self._resource(
            kind=kind,
            policy_id=policy_id,
            operation_id=operation_id,
            request_digest=request_digest,
            project_id=project_id,
            guide_id=guide_id,
            guide_version=guide_snapshot.version,
            generation=generation,
            final_digest=final_digest,
            predecessor_id=predecessor_id,
            predecessor_generation=predecessor_generation,
            predecessor_digest=predecessor_digest,
        )
        disposition, replay = await self._replay.reserve(
            actor_profile_id=resolved.profile.id,
            identity_link_id=resolved.identity_link.id,
            action_id=action.value,
            idempotency_key=key,
            request_digest=request_digest,
            policy_hash=final_digest,
            resource_context_digest=authorization_resource_digest(resource),
            operation_id=operation_id,
            project_id=str(project_id),
            guide_id=str(guide_id),
            policy_id=str(policy_id),
            policy_generation=generation,
        )
        if disposition != "claimed":
            if disposition == "mismatch":
                raise PolicyMutationConflict("idempotency_mismatch")
            if disposition == "pending" or replay.response_json is None:
                raise PolicyMutationConflict("idempotency_pending")
            return PolicyMutationOutcome(response_type.model_validate(replay.response_json), True)
        caller = PreparedAuthorizationInput(
            idempotency_key=key,
            request_value={
                "action_id": action.value,
                "project_id": str(project_id),
                "guide_id": str(guide_id),
                "policy_id": str(policy_id),
                "operation_id": str(operation_id),
                "request_digest": request_digest,
                "policy_digest": final_digest,
                "policy_generation": generation,
                "predecessor_policy_id": (
                    str(predecessor_id) if predecessor_id is not None else None
                ),
                "predecessor_policy_generation": predecessor_generation,
                "predecessor_policy_digest": predecessor_digest,
                "guide_status": "draft",
            },
        )
        try:
            handle = await prepared.prepare(
                action,
                caller,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=project_id,
                ),
            )
        except PreparedAuthorizationUnsupported as exc:
            await prepared.deny_unsupported(
                action,
                caller,
                ProjectPolicyMutationPrepareDenialResourceContext(
                    resource_type="project_policy_mutation_request",
                    resource_id=guide_id,
                    scope_project_id=project_id,
                    requested_guide_id=guide_id,
                    requested_policy_kind=kind,
                    request_digest=request_digest,
                ),
                exc,
            )
        guide = await self._projects.lock_project_guide(str(guide_id))
        if guide is None or guide.project_id != str(project_id):
            raise GuideNotFound("guide not found")
        if guide.status != "draft":
            raise GuideEditBlocked("only draft guides can change policy")
        current = (
            await self._projects.lock_review_policy(str(project_id), guide.version)
            if kind == "review"
            else await self._projects.lock_revision_policy(str(project_id), guide.version)
        )
        current_selector = self._guide_selector(kind, guide)
        if current_selector != expected_selector:
            raise PolicyMutationConflict("policy_precondition_failed")
        try:
            decision = await prepared.consume(handle, action, caller, resource)
        except PreparedAuthorizationHandleInvalid as exc:
            raise PolicyMutationConflict("authorization_handle_invalid") from exc
        self._prove(decision, project_id)
        common = {
            "id": str(policy_id),
            "project_id": str(project_id),
            "guide_version": guide.version,
            "policy_generation": generation,
            "policy_hash": final_digest,
            "semantics_status": "complete",
            "supersedes_policy_id": current.id if current is not None else None,
            "predecessor_policy_hash": predecessor_digest,
            "created_by_actor_profile_id": resolved.profile.id,
            "created_via_identity_link_id": resolved.identity_link.id,
            "created_by_admin_role_grant_id": decision.matched_grant_id,
            "creation_scope_type": (
                "system" if decision.matched_scope_project_id is None else "project"
            ),
            "creation_scope_project_id": (
                str(decision.matched_scope_project_id)
                if decision.matched_scope_project_id is not None
                else None
            ),
            "creation_action_id": action.value,
            "authorization_decision_event_id": str(decision.decision_id),
            **semantic_values,
        }
        policy = ReviewPolicy(**common) if kind == "review" else RevisionPolicy(**common)
        if kind == "review":
            await self._projects.add_review_policy_version(policy, guide)
        else:
            await self._projects.add_revision_policy_version(policy, guide)
        response = response_type.model_validate(policy)
        await self._replay.complete(replay, response_json=response.model_dump(mode="json"))
        return PolicyMutationOutcome(response, False)
