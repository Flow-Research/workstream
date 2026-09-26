"""Service layer for task queue lifecycle and assignment operations."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.modules.checkers.api.pre_submit import (
    EffectivePreSubmissionPlanningPort, EffectivePreSubmissionPlanLineage,
)
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy, PostSubmitCatalogue
from app.modules.projects.api.locked_policy import (
    ProjectLockedPolicyContextFacts, ProjectLockedPolicyContextPort,
    ProjectLockedPolicyContextRequest, ProjectLockedPolicyContextUnavailable,
)
from app.modules.tasks.lifecycle import (
    InvalidTaskTransition,
    ensure_allowed_transition,
)
from app.modules.tasks.models import (
    WorkstreamTask,
)
from app.modules.tasks.api.task_detail import ContributorTaskDetailRequest
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import (
    ForbiddenArtifactRequirement,
    PostSubmitPolicyBodySummary,
    RequiredArtifactRequirement,
    RequiredEvidenceRequirement,
    StorageReferenceRules,
    ContributorTaskSubmissionRequirements,
    ManagementTaskSubmissionRequirements,
    SubmissionPackagingRequirements,
    ManagementTaskLockedContext,
    TaskResponse,
)

SUBMISSION_CREATE_REQUIRED_PACKET_FIELDS = (
    "summary",
    "package_hash",
    "artifact_hash_manifest",
    "worker_attestation",
)
LOCKED_CONTEXT_REQUIRED_FIELDS = (
    "locked_guide_version",
    "locked_post_submit_checker_policy_id",
    "locked_post_submit_checker_policy_version",
    "locked_post_submit_checker_policy_hash",
    "locked_post_submit_checker_policy_body",
    "locked_review_policy_id",
    "locked_review_policy_generation",
    "locked_review_policy_hash",
    "locked_revision_policy_id",
    "locked_revision_policy_generation",
    "locked_revision_policy_hash",
    "locked_contribution_policy_version_id",
    "locked_guide_source_snapshot_id",
    "locked_guide_source_snapshot_hash",
    "locked_effective_project_submission_artifact_policy_id",
    "locked_effective_project_submission_artifact_policy_hash",
    "locked_pre_submit_checker_policy_id",
    "locked_pre_submit_checker_bundle_hash",
)


class TaskServiceError(Exception):
    """Base error for task service failures mapped to API responses."""

    status_code = 400


class TaskNotFound(TaskServiceError):
    """Raised when a task id does not match a stored task."""

    status_code = 404


class TaskProjectNotReady(TaskServiceError):
    """Raised when a project does not have active guide and policy context."""

    status_code = 422


class TaskTransitionBlocked(TaskServiceError):
    """Raised when a task lifecycle transition is blocked by policy."""

    status_code = 409


class TaskValidationError(TaskServiceError):
    """Raised when a task is missing fields required by its guide."""

    status_code = 422


class TaskAssignmentConflict(TaskServiceError):
    """Raised when a task already has an active Contributor assignment."""

    status_code = 409


class TaskLockedContextInvalid(TaskServiceError):
    """Raised when a task's stamped policy provenance is missing or inconsistent."""

    status_code = 422
    code = "task_locked_context_invalid"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Create a locked-context error with machine-readable details.

        Args:
            message: Human-readable error summary safe for API responses.
            details: Optional structured error details.
        """
        super().__init__(message)
        self.details = details or {"message": message}


@dataclass(frozen=True)
class LockedTaskContext:
    """Validated records bound to one task's stamped locked context."""

    facts: ProjectLockedPolicyContextFacts
    locked_post_submit_policy_body: PostSubmitPolicyBodySummary


class TaskService:
    """Coordinates task lifecycle rules, assignment, and audit writes."""

    def __init__(
        self, session: AsyncSession, *, project_contexts: ProjectLockedPolicyContextPort,
        pre_submit_planner: EffectivePreSubmissionPlanningPort, post_submit_catalogue: Callable[[], PostSubmitCatalogue],
    ) -> None:
        """Create a service instance bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current request.
        """
        self._project_contexts = project_contexts
        self._pre_submit_planner = pre_submit_planner
        self._post_submit_catalogue = post_submit_catalogue
        self._session = session
        self._repo = TaskRepository(session)

    async def read_management_task_submission_requirements(
        self, project_id: UUID, task_id: UUID,
    ) -> ManagementTaskSubmissionRequirements:
        """Read hidden management requirements in the caller's authorized transaction."""
        task, context = await self._read_locked_context(project_id, task_id)
        return ManagementTaskSubmissionRequirements(**self._submission_requirement_values(task, context))

    async def read_contributor_task_submission_requirements(
        self, project_id: UUID, task_id: UUID, contributor_id: UUID,
    ) -> ContributorTaskSubmissionRequirements:
        """Lock TASK, conceal invisible work, then validate historical policy custody."""
        request = ContributorTaskDetailRequest(project_id, task_id, contributor_id)
        with self._session.no_autoflush:
            task = await self._lock_scoped_task(project_id, task_id)
            detail = await self._repo.read_contributor_task_detail(request)
            if detail is None:
                raise TaskNotFound("task not found")
            context = await self._load_locked_task_context(task)
            return self._contributor_submission_requirements_response(task, context)

    async def _lock_scoped_task(self, project_id: UUID, task_id: UUID) -> WorkstreamTask:
        """Validate exact selectors and refresh a scoped TASK under the caller's lock."""
        if not isinstance(project_id, UUID) or not isinstance(task_id, UUID):
            raise ValueError("task locked context selectors are invalid")
        with self._session.no_autoflush:
            task = await self._repo.lock_project_task(project_id, task_id)
            if task is None:
                raise TaskNotFound("task not found")
            return task

    async def _read_locked_context(
        self, project_id: UUID, task_id: UUID,
    ) -> tuple[WorkstreamTask, LockedTaskContext]:
        """Resolve historical PROJECTS custody only after the shared TASK lock."""
        with self._session.no_autoflush:
            task = await self._lock_scoped_task(project_id, task_id)
            return task, await self._load_locked_task_context(task)


    async def _load_active_policy_context(self, project_id: str) -> ProjectLockedPolicyContextFacts:
        """Resolve exact activated custody and verify both installed checker plans."""
        try:
            facts = await self._project_contexts.lock_active_policy_context(UUID(project_id))
            self._validate_installed_plans(facts)
            return facts
        except (ProjectLockedPolicyContextUnavailable, ValueError) as exc:
            raise TaskProjectNotReady("active guide policy context is unavailable") from exc

    def _validate_installed_plans(self, facts: ProjectLockedPolicyContextFacts) -> None:
        """Check deployment capability before new readiness, without executing checks."""
        try:
            self._pre_submit_planner.compile_effective_plan(
                lineage=EffectivePreSubmissionPlanLineage(
                    project_id=facts.project_id, guide_id=facts.guide_id,
                    guide_version=facts.guide_version, source_snapshot_id=facts.source_snapshot_id,
                    source_snapshot_hash=facts.source_snapshot_hash,
                    effective_policy_id=facts.effective_policy_id,
                    effective_policy_hash=facts.effective_policy_hash,
                    pre_submit_policy_id=facts.pre_submit_policy_id,
                    pre_submit_policy_bundle_hash=facts.pre_submit_policy_bundle_hash,
                ),
                effective_policy=json.loads(facts.effective_policy.value),
                compiled_bundle=json.loads(facts.compiled_pre_submit_bundle.value),
            )
            CompiledPostSubmitPolicy.model_validate_json(
                facts.compiled_post_submit_policy.value,
            ).validate_catalogue(self._post_submit_catalogue())
        except ValueError as exc:
            raise TaskProjectNotReady("installed checkers cannot execute the locked policies") from exc

    async def _load_locked_task_context(self, task: WorkstreamTask) -> LockedTaskContext:
        """Resolve frozen custody without selecting current policy or deployment capabilities."""
        missing = self._missing_locked_context_fields(task)
        if missing:
            raise TaskLockedContextInvalid("task locked context is incomplete", {"missing_fields": missing})
        try:
            facts = await self._project_contexts.lock_locked_policy_context(
                ProjectLockedPolicyContextRequest(
                    project_id=UUID(task.project_id), guide_version=task.locked_guide_version,
                    source_snapshot_id=UUID(task.locked_guide_source_snapshot_id),
                    source_snapshot_hash=task.locked_guide_source_snapshot_hash,
                    effective_policy_id=UUID(task.locked_effective_project_submission_artifact_policy_id),
                    effective_policy_hash=task.locked_effective_project_submission_artifact_policy_hash,
                    pre_submit_policy_id=UUID(task.locked_pre_submit_checker_policy_id),
                    pre_submit_policy_bundle_hash=task.locked_pre_submit_checker_bundle_hash,
                ),
            )
            expected = self._policy_stamps(facts)
            if any(getattr(task, name) != value for name, value in expected.items()):
                raise ValueError("task policy stamps differ from activation receipt")
            parsed = CompiledPostSubmitPolicy.model_validate_json(facts.compiled_post_submit_policy.value)
        except (ProjectLockedPolicyContextUnavailable, ValueError, TypeError) as exc:
            raise TaskLockedContextInvalid("task locked policy custody is invalid") from exc
        return LockedTaskContext(
            facts=facts,
            locked_post_submit_policy_body=PostSubmitPolicyBodySummary(
                schema_version=parsed.schema_version, default_checkers=tuple(parsed.default_checkers),
                required_checkers=tuple(parsed.required_checkers), warning_checkers=tuple(parsed.warning_checkers),
                execution_checkers=tuple(parsed.execution_checkers),
                blocking_severities=tuple(parsed.blocking_severities),
            ),
        )

    def _missing_locked_context_fields(self, task: WorkstreamTask) -> list[str]:
        """Return missing locked-context fields for a task."""
        return [field for field in LOCKED_CONTEXT_REQUIRED_FIELDS if not getattr(task, field)]

    def _contributor_submission_requirements_response(
        self, task: WorkstreamTask, context: LockedTaskContext,
    ) -> ContributorTaskSubmissionRequirements:
        """Compose the contributor projection shared by hidden and retained reads."""
        return ContributorTaskSubmissionRequirements(**self._submission_requirement_values(task, context))

    def _submission_requirement_values(
        self,
        task: WorkstreamTask,
        context: LockedTaskContext,
    ) -> dict[str, object]:
        """Translate the historical effective policy once into fixed safe values."""
        policy = json.loads(context.facts.effective_policy.value)
        if not isinstance(policy, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": "effective_policy"},
            )
        allowed_storage_schemes = tuple(self._policy_string_list(policy, "allowed_storage_schemes"))
        required_artifacts = self._policy_list(policy, "required_artifacts")
        required_evidence = self._policy_list(policy, "required_evidence")
        forbidden_artifacts = self._policy_list(policy, "forbidden_artifacts")
        return dict(
            task_id=UUID(task.id),
            project_id=UUID(task.project_id),
            guide_version=task.locked_guide_version,
            policy_schema_version=self._optional_policy_text(policy, "schema_version"),
            merge_algorithm_version=self._optional_policy_text(
                policy,
                "merge_algorithm_version",
            ),
            required_packet_fields=tuple(self._required_packet_fields(policy)),
            required_artifacts=tuple(
                RequiredArtifactRequirement(
                    key=self._policy_rule_text(rule, "key", "required_artifacts"),
                    path=self._policy_rule_text(rule, "path", "required_artifacts"),
                    hash_required=self._policy_rule_bool(
                        rule,
                        "hash_required",
                        "required_artifacts",
                    ),
                    required=self._policy_rule_bool(
                        rule,
                        "required",
                        "required_artifacts",
                    ),
                    description=self._optional_policy_rule_text(
                        rule,
                        "description",
                        "required_artifacts",
                    ),
                )
                for rule in required_artifacts
            ),
            required_evidence=tuple(
                RequiredEvidenceRequirement(
                    key=self._policy_rule_text(rule, "key", "required_evidence"),
                    label=self._policy_rule_text(rule, "label", "required_evidence"),
                    hash_required=self._policy_rule_bool(
                        rule,
                        "hash_required",
                        "required_evidence",
                    ),
                    required=self._policy_rule_bool(
                        rule,
                        "required",
                        "required_evidence",
                    ),
                    description=self._optional_policy_rule_text(
                        rule,
                        "description",
                        "required_evidence",
                    ),
                )
                for rule in required_evidence
            ),
            forbidden_artifacts=tuple(
                ForbiddenArtifactRequirement(
                    pattern=self._policy_rule_text(rule, "pattern", "forbidden_artifacts"),
                    reason=self._optional_policy_rule_text(
                        rule,
                        "reason",
                        "forbidden_artifacts",
                    ),
                    worker_facing_fix=self._optional_policy_rule_text(
                        rule,
                        "worker_facing_fix",
                        "forbidden_artifacts",
                    ),
                    severity=self._optional_policy_rule_text(
                        rule,
                        "severity",
                        "forbidden_artifacts",
                    ),
                )
                for rule in forbidden_artifacts
            ),
            attestation_terms=tuple(self._policy_string_list(policy, "attestation_terms")),
            manifest_required=self._policy_bool(policy, "manifest_required"),
            artifact_hash_required=self._policy_bool(policy, "artifact_hash_required"),
            artifact_hash_algorithm="sha256",
            allowed_storage_schemes=allowed_storage_schemes,
            storage_reference_rules=StorageReferenceRules(
                allowed_storage_schemes=allowed_storage_schemes,
                allowed_uri_prefixes=tuple(f"{scheme}://" for scheme in allowed_storage_schemes),
                credentials_allowed=False,
                query_strings_allowed=False,
                fragments_allowed=False,
                path_traversal_allowed=False,
            ),
            maximum_file_size_bytes=self._optional_policy_non_negative_int(
                policy,
                "maximum_file_size_bytes",
            ),
            maximum_package_size_bytes=self._optional_policy_non_negative_int(
                policy,
                "maximum_package_size_bytes",
            ),
            packaging=self._packaging_requirements(policy),
            maximum_archive_entries=self._optional_policy_non_negative_int(
                policy, "maximum_archive_entries", minimum=1,
            ),
            maximum_archive_size_bytes=self._optional_policy_non_negative_int(
                policy, "maximum_archive_size_bytes", minimum=1,
            ),
        )

    def _packaging_requirements(self, policy: dict[str, Any]) -> SubmissionPackagingRequirements:
        """Validate the bounded packaging value without exposing arbitrary policy keys."""
        try:
            return SubmissionPackagingRequirements.model_validate_json(
                json.dumps(self._policy_object(policy, "packaging")),
            )
        except ValidationError as exc:
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": "effective_policy.packaging"},
            ) from exc

    def _policy_list(self, policy: dict[str, Any], field: str) -> list[Any]:
        """Return a list field from the locked policy or fail closed."""
        value = policy.get(field, [])
        if not isinstance(value, list):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _policy_string_list(self, policy: dict[str, Any], field: str) -> list[str]:
        """Return a string-list field from the locked policy or fail closed."""
        values = self._policy_list(policy, field)
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                raise TaskLockedContextInvalid(
                    "task locked effective project submission artifact policy is invalid",
                    {"field": f"effective_policy.{field}"},
                )
            normalized.append(value.strip())
        return normalized

    def _policy_bool(self, policy: dict[str, Any], field: str) -> bool:
        """Return a boolean field from the locked policy or fail closed."""
        value = policy.get(field, True)
        if not isinstance(value, bool):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _policy_object(self, policy: dict[str, Any], field: str) -> dict[str, Any]:
        """Return an object field from the locked policy or fail closed."""
        value = policy.get(field, {})
        if not isinstance(value, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return dict(value)

    def _optional_policy_text(self, policy: dict[str, Any], field: str) -> str | None:
        """Return an optional text field from the locked policy or fail closed."""
        value = policy.get(field)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _optional_policy_non_negative_int(
        self,
        policy: dict[str, Any],
        field: str,
        *, minimum: int = 0,
    ) -> int | None:
        """Return an optional non-negative integer from the locked policy."""
        value = policy.get(field)
        if value is None:
            return None
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{field}"},
            )
        return value

    def _required_packet_fields(self, policy: dict[str, Any]) -> list[str]:
        """Return exact submission packet fields required by API and policy."""
        required_fields: list[str] = []
        policy_fields = policy.get("required_packet_fields", [])
        if not isinstance(policy_fields, list):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": "effective_policy.required_packet_fields"},
            )
        for field in (*SUBMISSION_CREATE_REQUIRED_PACKET_FIELDS, *policy_fields):
            if not isinstance(field, str) or not field.strip():
                raise TaskLockedContextInvalid(
                    "task locked effective project submission artifact policy is invalid",
                    {"field": "effective_policy.required_packet_fields"},
                )
            normalized = field.strip()
            if normalized not in required_fields:
                required_fields.append(normalized)
        return required_fields

    def _policy_rule_text(self, rule: object, key: str, collection: str) -> str:
        """Return a required text field from a locked policy rule or fail closed."""
        if not isinstance(rule, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}"},
            )
        value = rule.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}.{key}"},
            )
        return value

    def _optional_policy_rule_text(
        self,
        rule: object,
        key: str,
        collection: str,
    ) -> str | None:
        """Return an optional text field from a locked policy rule."""
        if not isinstance(rule, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}"},
            )
        value = rule.get(key)
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}.{key}"},
            )
        return value

    def _policy_rule_bool(
        self,
        rule: object,
        key: str,
        collection: str,
    ) -> bool:
        """Return a boolean field from a locked policy rule or fail closed."""
        if not isinstance(rule, dict):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}"},
            )
        value = rule.get(key, True)
        if not isinstance(value, bool):
            raise TaskLockedContextInvalid(
                "task locked effective project submission artifact policy is invalid",
                {"field": f"effective_policy.{collection}.{key}"},
            )
        return value

    @staticmethod
    def _locked_context_reference_values(task: WorkstreamTask) -> dict[str, object]:
        """Copy only the fixed scalar projection after historical custody validation."""
        return {
            "task_id": UUID(task.id),
            "project_id": UUID(task.project_id),
            "locked_guide_version": task.locked_guide_version,
            "locked_guide_source_snapshot_id": UUID(task.locked_guide_source_snapshot_id),
            "locked_guide_source_snapshot_hash": task.locked_guide_source_snapshot_hash,
            "locked_effective_project_submission_artifact_policy_id": UUID(task.locked_effective_project_submission_artifact_policy_id),
            "locked_effective_project_submission_artifact_policy_hash": task.locked_effective_project_submission_artifact_policy_hash,
            "locked_pre_submit_checker_policy_id": UUID(task.locked_pre_submit_checker_policy_id),
            "locked_pre_submit_checker_bundle_hash": task.locked_pre_submit_checker_bundle_hash,
            "locked_post_submit_checker_policy_id": UUID(task.locked_post_submit_checker_policy_id),
            "locked_post_submit_checker_policy_version": task.locked_post_submit_checker_policy_version,
            "locked_post_submit_checker_policy_hash": task.locked_post_submit_checker_policy_hash,
            "locked_review_policy_id": UUID(task.locked_review_policy_id),
            "locked_review_policy_generation": task.locked_review_policy_generation,
            "locked_review_policy_hash": task.locked_review_policy_hash,
            "locked_revision_policy_id": UUID(task.locked_revision_policy_id),
            "locked_revision_policy_generation": task.locked_revision_policy_generation,
            "locked_revision_policy_hash": task.locked_revision_policy_hash,
            "locked_contribution_policy_version_id": task.locked_contribution_policy_version_id,
        }

    def _management_locked_context_response(
        self, task: WorkstreamTask, context: LockedTaskContext,
    ) -> ManagementTaskLockedContext:
        """Compose the sole management projection, shared by hidden and retained reads."""
        return ManagementTaskLockedContext(
            **self._locked_context_reference_values(task),
            locked_post_submit_checker_policy_body_summary=context.locked_post_submit_policy_body,
        )

    def _validate_task_contract_fields(self, task: WorkstreamTask) -> None:
        """Validate task source and reviewability fields before screening.

        Args:
            task: Task being screened.

        Raises:
            TaskValidationError: If one or more required fields are missing.
        """
        required_fields = {"title", "description", "acceptance_criteria"}
        field_values = {
            "title": task.title,
            "description": task.description,
            "acceptance_criteria": task.acceptance_criteria,
        }
        missing = [
            field
            for field in sorted(required_fields)
            if not self._field_has_value(field_values.get(field))
        ]
        if missing:
            raise TaskValidationError(f"task missing required fields: {', '.join(missing)}")

    @staticmethod
    def _field_has_value(value: object) -> bool:
        """Return whether a required field value is present.

        Args:
            value: Field value from the task model.

        Returns:
            ``True`` when the value should satisfy a required field.
        """
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list | tuple | set | dict):
            return bool(value)
        return True

    @staticmethod
    def _policy_stamps(facts: ProjectLockedPolicyContextFacts) -> dict[str, object]:
        """Project the single activation receipt and exact frozen inputs onto TASK locks."""
        command = facts.activation_receipt.command
        return {
            "locked_contribution_policy_version_id": command.contribution_policy_version_id,
            "locked_guide_version": facts.guide_version,
            "locked_post_submit_checker_policy_id": str(command.target.policy_id),
            "locked_post_submit_checker_policy_version": facts.guide_version,
            "locked_post_submit_checker_policy_hash": command.target.policy_hash,
            "locked_post_submit_checker_policy_body": json.loads(facts.compiled_post_submit_policy.value),
            "locked_review_policy_id": str(command.review.policy_id),
            "locked_review_policy_generation": command.review.generation,
            "locked_review_policy_hash": command.review.policy_hash,
            "locked_revision_policy_id": str(command.revision.policy_id),
            "locked_revision_policy_generation": command.revision.generation,
            "locked_revision_policy_hash": command.revision.policy_hash,
            "locked_guide_source_snapshot_id": str(facts.source_snapshot_id),
            "locked_guide_source_snapshot_hash": facts.source_snapshot_hash,
            "locked_effective_project_submission_artifact_policy_id": str(facts.effective_policy_id),
            "locked_effective_project_submission_artifact_policy_hash": facts.effective_policy_hash,
            "locked_pre_submit_checker_policy_id": str(facts.pre_submit_policy_id),
            "locked_pre_submit_checker_bundle_hash": facts.pre_submit_policy_bundle_hash,
        }

    def _stamp_locked_context(self, task: WorkstreamTask, facts: ProjectLockedPolicyContextFacts) -> None:
        """Copy the exact activated context without obsolete PaymentPolicy readiness."""
        for name, value in self._policy_stamps(facts).items():
            setattr(task, name, value)

    def _ensure_locked_context(self, task: WorkstreamTask) -> None:
        """Ensure all guide and policy version fields are locked.

        Args:
            task: Task whose locked context should be checked.

        Raises:
            TaskTransitionBlocked: If any context field is missing.
        """
        missing = self._missing_locked_context_fields(task)
        if missing:
            raise TaskTransitionBlocked(f"task missing locked context: {', '.join(missing)}")


    @staticmethod
    def task_response_for_authority(task: WorkstreamTask, *, can_manage: bool) -> TaskResponse:
        """Use an explicit authorized projection, never inferred token roles."""
        response = TaskResponse.model_validate(task)
        if not can_manage:
            response.source_ref = None
            response.source_payload_hash = None
            response.import_batch_id = None
            response.external_task_id = None
            response.created_by = None
            response.assigned_to = None
            response.locked_guide_source_snapshot_id = None
            response.locked_guide_source_snapshot_hash = None
            response.locked_effective_project_submission_artifact_policy_id = None
            response.locked_effective_project_submission_artifact_policy_hash = None
            response.locked_pre_submit_checker_policy_id = None
            response.locked_pre_submit_checker_bundle_hash = None
        return response


    def _ensure_transition_allowed(self, from_status: str, to_status: str) -> None:
        """Map lifecycle transition validation into service-layer errors.

        Args:
            from_status: Current task status.
            to_status: Desired next task status.

        Raises:
            TaskTransitionBlocked: If the transition is not implemented by this chunk.
        """
        try:
            ensure_allowed_transition(from_status, to_status)
        except InvalidTaskTransition as exc:
            raise TaskTransitionBlocked(str(exc)) from exc
