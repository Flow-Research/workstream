"""Verified post-submit input through the sole bounded artifact scratch owner."""

import asyncio
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_cancellation_resistant, run_blocking_cancellation_resistant
from app.core.hashing import canonical_json_hash
from app.interfaces.artifacts import (
    ArtifactStore, ArtifactObjectMissingError, ArtifactInputMismatchError,
    ArtifactIntegrityError, ArtifactLimitExceededError, ArtifactStoreUnavailableError,
)
from app.interfaces.external_checker_execution import ExternalCheckerMaterialGrant
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterialConsumer, PostSubmissionMaterializationResult,
    PostSubmissionMaterializationUnavailable, PostSubmissionMaterializationFailure,
    SubmissionMaterialEntry, MaterializationFacts, MaterializationMaterialFacts, MaterializationAuthorityPort, PreparedMaterialization,
    materialization_input_context,
)
from app.modules.artifacts.post_submit_selection import (
    PostSubmissionMaterialSelection, read_post_submission_facts,
    read_consumed_revision_selector, select_admitted_post_material, select_predecessor_material,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchIntegrityError
from app.modules.artifacts.preparation import (
    ExternalMaterialFile,
    PostExternalMaterialGrantRequest, PostExternalMaterialGrantItem,
)
from app.modules.artifacts.service import ArtifactStorageNamespaceError, ArtifactStorageNamespaceSpec
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspector, SubmissionArchiveRejectedError,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.evaluation_contract import (
    validate_execution_result,
)
from app.modules.checkers.api.execution import (
    ExecuteFacts, CurrentExecutionPort, VerifiedMaterialFacts, CheckerExecutionUnavailable,
)
from app.modules.tasks.api.submitted_bundle import SubmittedBundlePort, SubmittedBundleUnavailable
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    PostSubmitExternalCheckerIdentity,
    PostSubmitExternalCheckerMaterial,
)

from app.modules.tasks.api.evaluation_revision import TaskEvaluationRevisionContext, TaskEvaluationRevisionPort
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest
from app.modules.checkers.api.evaluation_context import PostSubmitEvaluationContext, PostSubmitEvaluationPredecessor
from app.modules.checkers.api.external_policy import LockedExternalCheckerBinding, selected_evaluation_context_roles
from app.modules.checkers.api.revision_feedback import RevisionFeedbackPort, RevisionFeedbackRequest
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmitCurrentResultReference


def _external_material(facts, media_type, role):
    """Project verified custody without provider coordinates or file paths."""
    material = facts.material
    return PostSubmitExternalCheckerMaterial(
        role=role, submission_id=material.submission_id,
        submission_version=material.submission_version, binding_id=material.binding_id,
        content_id=material.content_id, replica_id=material.replica_id,
        content_sha256=material.content_sha256, byte_count=material.byte_count,
        media_type=media_type, evidence_id=facts.evidence_id,
        verification_receipt_id=facts.verification_receipt_id,
        verification_job_id=facts.verification_job_id,
        verification_generation=facts.verification_generation,
        namespace_fingerprint=facts.namespace_fingerprint,
        semantic_manifest_sha256=material.semantic_manifest_sha256,
    )


@dataclass(frozen=True)
class _MaterialSelection:
    """Exact detached owner facts, revalidated together after all provider I/O."""

    current: PostSubmissionMaterialSelection
    revision: TaskEvaluationRevisionContext | None
    predecessor: PostSubmissionMaterialSelection | None
    context: PostSubmitEvaluationContext | None


class _MaterialView:
    """One aggregate projection with per-binding least-material grants."""

    def __init__(self, trees, *, preparation, sources, workspace,
                 execution, materialization, media_types):
        self._trees = trees
        self._tree = trees["submission_archive"]
        self._preparation, self._sources, self._workspace = preparation, sources, workspace
        self._execution, self._materialization = execution, materialization
        self._materials = (_external_material(materialization, media_types["submission_archive"], "submission_archive"),)
        if materialization.predecessor is not None:
            self._materials += (_external_material(materialization.predecessor, media_types["predecessor_submission_archive"], "predecessor_submission_archive"),)
        self._closed = False

    def close(self):
        """Revoke every view before the aggregate projection is cleaned."""
        self._closed = True

    def _require_open(self):
        if self._closed:
            raise RuntimeError("submission material view is closed")

    @property
    def entries(self):
        """Current-only manifest; prior content never changes the current input tree."""
        self._require_open()
        return tuple(SubmissionMaterialEntry(
            item.normalized_path, item.entry_type.value, item.byte_count, item.sha256, item.executable,
        ) for item in self._tree.entries)

    def read_file(self, normalized_path, *, maximum_bytes):
        """Read current work only; a checker needs an approved role for prior bytes."""
        self._require_open()
        return self._tree.read_file(normalized_path, maximum_bytes=maximum_bytes)

    @property
    def external_checker_material(self):
        self._require_open()
        return self._materials[0]

    def _binding(self, requested):
        checked = LockedExternalCheckerBinding.model_validate(requested)
        if checked not in self._execution.request.policy.entries:
            raise ArtifactScratchIntegrityError("external POST policy binding differs")
        return checked

    def evaluation_material(self, binding):
        """Filter the aggregate owner context to the exact approved binding."""
        self._require_open()
        binding = self._binding(binding)
        roles = selected_evaluation_context_roles(binding.configuration, binding.stage)
        context = self._materialization.evaluation_context
        if roles is None or context is None:
            raise ArtifactScratchIntegrityError("external POST context was not selected")
        context = PostSubmitEvaluationContext.model_validate(context.model_copy(update={
            "feedback": context.feedback if "predecessor_findings" in roles else None,
        }))
        materials = self._materials[:1]
        if context.kind == "checker_remediation" and "predecessor_submission_archive" in roles:
            if len(self._materials) != 2:
                raise ArtifactScratchIntegrityError("external POST prior material is unavailable")
            materials = self._materials
        return context, materials

    @contextmanager
    def external_checker_grant(self, request):
        """Bind one manifest to actual execution, approved policy and visible role facts."""
        self._require_open()
        checked = ExternalCheckerExecutionRequest.model_validate(request)
        identity, source = checked.identity, self._execution.request
        lease = self._execution.lease
        reservation = lease.reservation
        expected_identity = PostSubmitExternalCheckerIdentity(
            project_id=source.project_id, task_id=source.task_id, assignment_id=source.assignment_id,
            submission_id=source.submission_id, submission_version=source.submission_version,
            evaluation_request_id=source.evaluation_request_id, evaluation_request_digest=source.request_sha256,
            evaluation_generation=source.evaluation_generation, attempt_id=reservation.attempt_id,
            result_id=reservation.result_id, lease_id=lease.lease_id,
            lease_generation=lease.lease_generation, lease_expires_at=lease.expires_at,
        )
        if identity != expected_identity:
            raise ArtifactScratchIntegrityError("external POST execution identity differs")
        matches = [binding for binding in source.policy.entries if (
            binding.requirement_id == checked.input.get("requirement_id")
            and binding.registry == checked.registry
            and binding.configuration == checked.configuration
            and binding.configuration_sha256 == checked.configuration_sha256
        )]
        if len(matches) != 1:
            raise ArtifactScratchIntegrityError("external POST policy binding differs")
        binding = matches[0]
        context, materials = None, self._materials[:1]
        if selected_evaluation_context_roles(binding.configuration, binding.stage) is not None:
            context, materials = self.evaluation_material(binding)
        if checked.materials != materials or checked.input.get("evaluation_context") != (
            context.model_dump(mode="json") if context is not None else None
        ):
            raise ArtifactScratchIntegrityError("external POST material identity differs")
        items = []
        for material in self._materials:
            entries = self._trees[material.role].entries
            items.append(PostExternalMaterialGrantItem(
                material=material,
                directories=tuple(item.normalized_path for item in entries if item.entry_type.value == "directory"),
                files=tuple(ExternalMaterialFile(
                    normalized_path=item.normalized_path, byte_count=item.byte_count,
                    sha256=item.sha256 or "", executable=bool(item.executable),
                ) for item in entries if item.entry_type.value == "file"),
            ))
        grant_request = PostExternalMaterialGrantRequest(
            request_digest=checked.request_digest, identity=identity,
            evaluation_context_sha256=canonical_json_hash(context.model_dump(mode="json")) if context else None,
            materials=tuple(items), visible_roles=tuple(item.role for item in materials),
        )
        with self._preparation.post_external_material_grant(self._sources, self._workspace, grant_request) as grant:
            yield ExternalCheckerMaterialGrant(grant_id=grant.grant_id, binding_digest=grant.binding_digest)

    def __reduce__(self):
        raise TypeError("submission material view is process-local")

    def validate_evaluation(self, result):
        """Bind retained input receipts to the actual authorized role projection."""
        if result.execution is None:
            return
        for binding, member in zip(self._execution.request.policy.entries, result.execution.external_members, strict=True):
            if selected_evaluation_context_roles(binding.configuration, binding.stage) is None:
                continue
            context, materials = self.evaluation_material(binding)
            receipt = member.input_receipt
            if (
                receipt is None
                or receipt.evaluation_context_sha256 != canonical_json_hash(context.model_dump(mode="json"))
                or receipt.materials != materials
            ):
                raise PostSubmissionMaterializationFailure("post_submit_input_receipt_mismatch")


class _MaterialProcessor:
    """Keep every role projection and selected image inside one cleanup lifetime."""

    def __init__(self, inspector, inspections, request, consumer, *, preparation, sources,
                 execution, materialization, media_types):
        self._inspector, self._inspections = inspector, inspections
        self._request, self._consumer = request, consumer
        self._preparation, self._sources = preparation, sources
        self._execution, self._materialization = execution, materialization
        self._media_types = media_types
        self._aborted = False
        self._consumer_task = None
        self._view = None

    def abort(self):
        if self._view is not None:
            self._view.close()
        self._aborted = True
        if self._consumer_task is not None:
            self._consumer_task.cancel()

    async def process(self, readers, workspace):
        """Project fixed private roots once; per-binding grants never move these trees."""
        projections, trees = [], {}
        try:
            materials_root = workspace / "materials"
            await run_blocking_cancellation_resistant(materials_root.mkdir, mode=0o700)
            for role, inspection in self._inspections.items():
                role_root = materials_root / role
                await run_blocking_cancellation_resistant(role_root.mkdir, mode=0o700)
                projection = self._inspector._projected_tree(readers[role], role_root, expected=inspection)

                def enter_projection():
                    tree = projection.__enter__()
                    projections.append(projection)
                    return tree

                tree = await run_blocking_cancellation_resistant(enter_projection)
                trees[role] = tree
                if self._aborted:
                    raise asyncio.CancelledError
            self._view = _MaterialView(
                trees, preparation=self._preparation, sources=self._sources, workspace=workspace,
                execution=self._execution, materialization=self._materialization, media_types=self._media_types,
            )
            self._consumer_task = asyncio.create_task(self._consumer.evaluate(self._request, self._view))
            result = validate_execution_result(await self._consumer_task)
            result.validate_request(self._request)
            self._view.validate_evaluation(result)
            return result
        finally:
            if self._view is not None:
                self._view.close()
            async def close_projections():
                failures = []
                for projection in reversed(projections):
                    try:
                        await asyncio.to_thread(projection.__exit__, None, None, None)
                    except Exception as error:
                        failures.append(error)
                if failures:
                    raise ArtifactScratchIntegrityError("post_submit_projection_cleanup_unconfirmed") from failures[0]
            await await_cancellation_resistant(close_projections())


class PostSubmissionMaterializer:
    """Resolve, authorize, verify, scope, clean, and revalidate one exact input."""

    def __init__(
        self, *, sessions: async_sessionmaker[AsyncSession],
        tasks: Callable[[AsyncSession], SubmittedBundlePort], store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec, preparation: ArtifactPreparationService,
        inspector: SubmissionArchiveInspector,
        authority: Callable[[AsyncSession], MaterializationAuthorityPort],
        current_execution: Callable[[AsyncSession], CurrentExecutionPort],
        revision_tasks: Callable[[AsyncSession], TaskEvaluationRevisionPort],
        revision_feedback: Callable[[AsyncSession], RevisionFeedbackPort],
    ) -> None:
        """Require explicit owner ports, scratch service and material authority."""
        self._sessions, self._tasks, self._store = sessions, tasks, store
        self._namespace, self._preparation = namespace, preparation
        self._inspector, self._authority = inspector, authority
        self._current_execution = current_execution
        self._revision_tasks, self._revision_feedback = revision_tasks, revision_feedback

    @staticmethod
    def _material_facts(selected):
        """Project exact selected ancestry without exposing ART provider coordinates."""
        submission = selected.submission
        return MaterializationMaterialFacts(
            material=VerifiedMaterialFacts(
                submission_id=submission.submission_id, submission_version=submission.submission_version,
                admission_id=submission.admission_id, binding_id=submission.binding_id,
                content_id=submission.content_id, replica_id=selected.replica_id,
                content_sha256=selected.sha256, byte_count=selected.byte_count,
                semantic_manifest_sha256=selected.semantic_manifest_sha256,
            ),
            evidence_id=selected.evidence_id, verification_receipt_id=selected.verification_receipt_id,
            verification_job_id=selected.verification_job_id,
            verification_generation=selected.verification_generation,
            namespace_fingerprint=selected.namespace_fingerprint,
            semantic_manifest_id=selected.semantic_manifest_id,
        )

    @classmethod
    def _authority_facts(cls, execution, selected):
        """Bind aggregate context and only policy-selected prior byte custody."""
        roles = {role for binding in execution.request.policy.entries
                 for role in (selected_evaluation_context_roles(binding.configuration, binding.stage) or ())}
        return MaterializationFacts(
            **cls._material_facts(selected.current).model_dump(), execution=execution,
            evaluation_context=selected.context,
            predecessor=(cls._material_facts(selected.predecessor)
                         if selected.predecessor is not None and "predecessor_submission_archive" in roles else None),
        )

    async def _select(self, facts, *, original=None, evidence_id=None):
        """AUTH -> TASK sources -> CHECKERS lease -> exact ART facts, closed before I/O."""
        try:
            async with self._sessions() as session, session.begin():
                async with self._authority(session).prepare_materialization(facts) as prepared:
                    if not isinstance(prepared, PreparedMaterialization):
                        raise PostSubmissionMaterializationUnavailable("post_submit_materialization_unavailable")
                    task_facts = await read_post_submission_facts(self._tasks(session), facts.request)
                    selections = tuple(selected_evaluation_context_roles(binding.configuration, binding.stage)
                                       for binding in facts.request.policy.entries)
                    roles = {role for selection in selections if selection is not None for role in selection}
                    revision, selector, prior_facts = None, None, None
                    if any(selection is not None for selection in selections):
                        selector = await read_consumed_revision_selector(session, task_facts)
                        revision = await self._revision_tasks(session).read(selector)
                        if revision.predecessor is not None:
                            prior_facts = await self._tasks(session).read(SubmittedBundleRequest(
                                project_id=revision.predecessor.project_id,
                                task_id=revision.predecessor.task_id,
                                submission_id=revision.predecessor.submission_id,
                            ))
                    await self._current_execution(session).require_current_execution(facts)
                    feedback = None
                    if revision is not None and revision.kind == "checker_remediation" and "predecessor_findings" in roles:
                        source = revision.source.evaluation
                        feedback = await self._revision_feedback(session).read(RevisionFeedbackRequest(
                            project_id=source.project_id, task_id=source.task_id,
                            assignment_id=revision.current.assignment_id,
                            submission_id=source.submission_id, submission_version=source.submission_version,
                            completion_event_id=source.completion_event_id,
                            result=SelectedPostSubmitCurrentResultReference(
                                request_id=source.evaluation_request_id,
                                request_digest=source.evaluation_request_digest,
                                attempt_id=source.checker_run_id, evaluation_generation=source.evaluation_generation,
                                result_id=source.result_id, result_digest=source.result_digest,
                            ),
                        ))
                    current = await select_admitted_post_material(
                        session, facts=task_facts, namespace=self._namespace, store=self._store,
                    )
                    if (current.sha256, current.byte_count) != (facts.request.content_sha256, facts.request.byte_count):
                        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
                    if selector is not None and (
                        current.revision_preparation_id, current.revision_preparation_sha256,
                    ) != (selector.preparation_id, selector.preparation_sha256):
                        raise PostSubmissionMaterializationUnavailable("post_submit_material_changed")
                    predecessor, context = None, None
                    if revision is not None:
                        prior_reference = None
                        if prior_facts is not None:
                            predecessor = await select_predecessor_material(
                                session, facts=prior_facts, context=revision, namespace=self._namespace, store=self._store,
                            )
                            prior_reference = PostSubmitEvaluationPredecessor(
                                submission_id=predecessor.submission.submission_id,
                                submission_version=predecessor.submission.submission_version,
                                content_sha256=predecessor.sha256, byte_count=predecessor.byte_count,
                                semantic_manifest_sha256=predecessor.semantic_manifest_sha256,
                            )
                        context = PostSubmitEvaluationContext(
                            kind=revision.kind,
                            source=revision.source.model_dump() if revision.source is not None else None,
                            predecessor=prior_reference, feedback=feedback,
                        )
                    selected = _MaterialSelection(current=current, revision=revision, predecessor=predecessor, context=context)
                    authority_facts = self._authority_facts(facts, selected)
                    if original is None:
                        evidence_id = await prepared.consume(authority_facts)
                    else:
                        if selected != original:
                            raise PostSubmissionMaterializationUnavailable("post_submit_material_changed")
                        await prepared.validate_replay(authority_facts, evidence_id)
                    return selected, evidence_id
        except (SubmittedBundleUnavailable, ArtifactStorageNamespaceError, CheckerExecutionUnavailable, ValueError):
            raise PostSubmissionMaterializationUnavailable("post_submit_material_unavailable") from None

    async def materialize(
        self,
        facts: ExecuteFacts,
        consumer: PostSubmissionMaterialConsumer,
    ) -> PostSubmissionMaterializationResult:
        """Verify bytes, run the scoped consumer, clean up, and reject late drift."""
        facts = ExecuteFacts.model_validate_json(facts.model_dump_json())
        request = facts.request
        selected, evidence_id = await self._select(facts)
        sources = []
        failure = None
        try:
            try:
                materialization_facts = self._authority_facts(facts, selected)
                selections = {"submission_archive": selected.current}
                if materialization_facts.predecessor is not None:
                    selections["predecessor_submission_archive"] = selected.predecessor
                inspections, media_types = {}, {}
                expanded_bytes, entries = 0, 0
                for role, selection in selections.items():
                    prepared = await self._preparation.prepare(
                        self._store.open(selection.provider_object_ref), media_type=selection.media_type,
                        expected_sha256=selection.sha256, expected_size=selection.byte_count,
                    )
                    sources.append((role, prepared))
                    inspection = await prepared.inspect(self._inspector)
                    manifest = build_submission_manifest(inspection)
                    if manifest.sha256 != selection.semantic_manifest_sha256:
                        raise PostSubmissionMaterializationFailure("post_submit_material_manifest_mismatch")
                    expanded_bytes += manifest.total_expanded_bytes
                    entries += manifest.entry_count
                    if (
                        expanded_bytes > self._inspector._limits.maximum_expanded_bytes
                        or entries > self._inspector._limits.maximum_entries
                    ):
                        raise ArtifactLimitExceededError("post_submit_aggregate_material_limit")
                    inspections[role], media_types[role] = inspection, selection.media_type
                evaluation = await self._preparation._process_prepared_post_submission(
                    tuple(sources), _MaterialProcessor(
                        self._inspector, inspections, request, consumer,
                        preparation=self._preparation, sources=tuple(sources),
                        execution=facts, materialization=materialization_facts,
                        media_types=media_types,
                    ),
                    reserved_bytes=expanded_bytes,
                    # Aggregate materials root, each role root and one temporary grant.
                    maximum_entries=entries + len(sources) + 2,
                )
            finally:
                async def close_sources():
                    failures = []
                    for _, prepared in reversed(sources):
                        try:
                            await prepared.close()
                        except Exception as error:
                            failures.append(error)
                    if failures:
                        raise ArtifactScratchIntegrityError("post_submit_source_cleanup_unconfirmed") from failures[0]
                await await_cancellation_resistant(close_sources())
        except asyncio.CancelledError:
            # The executor may convert its deadline cancellation into a terminal
            # timeout. Validate the completed read before allowing that conversion.
            # Denial/drift must win over cancellation; cleanup has already finished.
            await await_cancellation_resistant(
                self._select(facts, original=selected, evidence_id=evidence_id)
            )
            raise
        except ArtifactScratchIntegrityError:
            # Unconfirmed cleanup must never become a retained terminal result.
            raise
        except PostSubmissionMaterializationFailure as error:
            failure = error
        except (
            ArtifactObjectMissingError, ArtifactInputMismatchError, ArtifactIntegrityError,
            ArtifactLimitExceededError, ArtifactStoreUnavailableError, SubmissionArchiveRejectedError,
        ) as error:
            failure = PostSubmissionMaterializationFailure("post_submit_material_unavailable")
            failure.__cause__ = error
        await self._select(facts, original=selected, evidence_id=evidence_id)
        if failure is not None:
            raise failure
        current = selected.current
        facts = current.submission
        return PostSubmissionMaterializationResult(
            submission_id=facts.submission_id,
            submission_version=facts.submission_version,
            admission_id=facts.admission_id,
            binding_id=facts.binding_id,
            content_id=facts.content_id,
            replica_id=current.replica_id,
            content_sha256=current.sha256,
            byte_count=current.byte_count,
            semantic_manifest_sha256=current.semantic_manifest_sha256,
            evaluation=evaluation,
            input_materialization_evidence_id=evidence_id,
            input_context_custody=materialization_input_context(materialization_facts),
        )
