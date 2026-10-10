"""Verified post-submit input through the sole bounded artifact scratch owner."""

import asyncio
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.artifacts import (
    ArtifactStore, ArtifactObjectMissingError, ArtifactInputMismatchError,
    ArtifactIntegrityError, ArtifactLimitExceededError, ArtifactStoreUnavailableError,
)
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterialConsumer, PostSubmissionMaterializationResult,
    PostSubmissionMaterializationUnavailable, PostSubmissionMaterializationFailure,
    SubmissionMaterialEntry, MaterializationFacts, MaterializationAuthorityPort, PreparedMaterialization,
)
from app.modules.artifacts.post_submit_selection import (
    select_post_submission_material,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchIntegrityError
from app.modules.artifacts.service import ArtifactStorageNamespaceError, ArtifactStorageNamespaceSpec
from app.modules.artifacts.submission_archive import (
    SealedSubmissionTree, SubmissionArchiveInspector, SubmissionArchiveEntryType,
    SubmissionArchiveRejectedError,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api import PostSubmissionEvaluationResult
from app.modules.checkers.api.execution import (
    ExecuteFacts, CurrentExecutionPort, VerifiedMaterialFacts, CheckerExecutionUnavailable,
)
from app.modules.tasks.api.submitted_bundle import SubmittedBundlePort, SubmittedBundleUnavailable


class _MaterialView:
    """Revoke callback access independently of the private projection lifetime."""
    def __init__(self, tree: SealedSubmissionTree) -> None:
        """Wrap the single ART-owned sealed tree without exposing its path."""
        self._tree = tree
        self._closed = False

    def close(self) -> None:
        """Revoke subsequent metadata and file reads."""
        self._closed = True

    def _require_open(self) -> None:
        """Reject retained views after callback completion or cancellation."""
        if self._closed:
            raise RuntimeError("submission material view is closed")

    @property
    def entries(self) -> tuple[SubmissionMaterialEntry, ...]:
        """Project verified metadata while the view remains live."""
        self._require_open()
        return tuple(SubmissionMaterialEntry(
            item.normalized_path, item.entry_type.value, item.byte_count, item.sha256, item.executable,
        ) for item in self._tree.entries)

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        """Delegate bounded reads to the sealed verified tree."""
        self._require_open()
        return self._tree.read_file(normalized_path, maximum_bytes=maximum_bytes)

    def __reduce__(self):
        """Prevent transfer of a process-local read capability."""
        raise TypeError("submission material view is process-local")


class _MaterialProcessor:
    """Keep async evaluation inside the shared projection and scratch lifetime."""
    def __init__(self, inspector, inspection, request, consumer) -> None:
        """Bind one inspection, request and consumer for preparation-owned execution."""
        self._inspector, self._inspection = inspector, inspection
        self._request, self._consumer = request, consumer
        self._aborted = False
        self._consumer_task: asyncio.Task[PostSubmissionEvaluationResult] | None = None
        self._view: _MaterialView | None = None

    def abort(self) -> None:
        """Revoke reads and cancel the consumer before preparation drains cleanup."""
        self._aborted = True
        if self._view is not None:
            self._view.close()
        if self._consumer_task is not None:
            self._consumer_task.cancel()

    async def process(self, reader, workspace) -> PostSubmissionEvaluationResult:
        """Project off-loop, validate callback output, and drain projection cleanup."""
        projection = self._inspector._projected_tree(reader, workspace, expected=self._inspection)
        # The preparation owner shields and drains this entire operation, including
        # projection entry, before it releases the reader or workspace.
        tree = await asyncio.to_thread(projection.__enter__)
        try:
            if self._aborted:
                raise asyncio.CancelledError
            self._view = _MaterialView(tree)
            self._consumer_task = asyncio.create_task(self._consumer.evaluate(self._request, self._view))
            result = PostSubmissionEvaluationResult.model_validate(await self._consumer_task)
            result.validate_request(self._request)
            return result
        finally:
            if self._view is not None:
                self._view.close()
            try:
                await await_cancellation_resistant(asyncio.to_thread(projection.__exit__, None, None, None))
            except ArtifactScratchIntegrityError:
                raise
            except Exception:
                raise ArtifactScratchIntegrityError("post_submit_projection_cleanup_unconfirmed") from None


class PostSubmissionMaterializer:
    """Resolve, authorize, verify, scope, clean, and revalidate one exact input."""

    def __init__(
        self, *, sessions: async_sessionmaker[AsyncSession],
        tasks: Callable[[AsyncSession], SubmittedBundlePort], store: ArtifactStore,
        namespace: ArtifactStorageNamespaceSpec, preparation: ArtifactPreparationService,
        inspector: SubmissionArchiveInspector,
        authority: Callable[[AsyncSession], MaterializationAuthorityPort],
        current_execution: Callable[[AsyncSession], CurrentExecutionPort],
    ) -> None:
        """Require explicit owner ports, scratch service and material authority."""
        self._sessions, self._tasks, self._store = sessions, tasks, store
        self._namespace, self._preparation = namespace, preparation
        self._inspector, self._authority = inspector, authority
        self._current_execution = current_execution

    @staticmethod
    def _authority_facts(execution, selected):
        """Project exact selected ancestry without exposing ART provider coordinates."""
        submission = selected.submission
        return MaterializationFacts(
            execution=execution,
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

    async def _select(self, facts, *, original=None, evidence_id=None):
        """AUTH -> current CHECKERS lease -> ART selection, all closed before I/O."""
        try:
            async with self._sessions() as session, session.begin():
                async with self._authority(session).prepare_materialization(facts) as prepared:
                    if not isinstance(prepared, PreparedMaterialization):
                        raise PostSubmissionMaterializationUnavailable("post_submit_materialization_unavailable")
                    await self._current_execution(session).require_current_execution(facts)
                    selected = await select_post_submission_material(
                        session, tasks=self._tasks(session), request=facts.request,
                        namespace=self._namespace, store=self._store,
                    )
                    authority_facts = self._authority_facts(facts, selected)
                    if original is None:
                        evidence_id = await prepared.consume(authority_facts)
                    else:
                        if selected != original:
                            raise PostSubmissionMaterializationUnavailable("post_submit_material_changed")
                        await prepared.validate_replay(authority_facts, evidence_id)
                    return selected, evidence_id
        except (SubmittedBundleUnavailable, ArtifactStorageNamespaceError, CheckerExecutionUnavailable):
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
        prepared = None
        failure = None
        try:
            try:
                prepared = await self._preparation.prepare(
                    self._store.open(selected.provider_object_ref), media_type=selected.media_type,
                    expected_sha256=selected.sha256, expected_size=selected.byte_count,
                )
                inspection = await prepared.inspect(self._inspector)
                manifest = build_submission_manifest(inspection)
                expected_files = tuple((entry.normalized_path, entry.sha256, entry.byte_count)
                                       for entry in manifest.entries
                                       if entry.entry_type is SubmissionArchiveEntryType.FILE)
                supplied_files = tuple(sorted((entry.artifact, entry.hash, entry.size_bytes)
                                              for entry in request.structural_input.manifest))
                if manifest.sha256 != selected.semantic_manifest_sha256 or supplied_files != expected_files:
                    raise PostSubmissionMaterializationFailure("post_submit_material_manifest_mismatch")
                evaluation = await self._preparation._process_prepared_submission(
                    prepared, _MaterialProcessor(self._inspector, inspection, request, consumer),
                    reserved_bytes=manifest.total_expanded_bytes, maximum_entries=manifest.entry_count,
                )
            finally:
                if prepared is not None:
                    try:
                        await prepared.close()
                    except ArtifactScratchIntegrityError:
                        raise
                    except Exception:
                        raise ArtifactScratchIntegrityError("post_submit_source_cleanup_unconfirmed") from None
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
        ):
            failure = PostSubmissionMaterializationFailure("post_submit_material_unavailable")
        await self._select(facts, original=selected, evidence_id=evidence_id)
        if failure is not None:
            raise failure
        facts = selected.submission
        return PostSubmissionMaterializationResult(
            submission_id=facts.submission_id,
            submission_version=facts.submission_version,
            admission_id=facts.admission_id,
            binding_id=facts.binding_id,
            content_id=facts.content_id,
            replica_id=selected.replica_id,
            content_sha256=selected.sha256,
            byte_count=selected.byte_count,
            semantic_manifest_sha256=selected.semantic_manifest_sha256,
            evaluation=evaluation,
            input_materialization_evidence_id=evidence_id,
        )
