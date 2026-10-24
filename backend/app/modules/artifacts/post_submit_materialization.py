"""Verified post-submit input through the sole bounded artifact scratch owner."""

import asyncio
from collections.abc import Callable
from contextlib import contextmanager, AsyncExitStack

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cancellation import await_cancellation_resistant
from app.interfaces.artifacts import (
    ArtifactStore, ArtifactObjectMissingError, ArtifactInputMismatchError,
    ArtifactIntegrityError, ArtifactLimitExceededError, ArtifactStoreUnavailableError,
)
from app.interfaces.external_checker_execution import ExternalCheckerMaterialGrant
from app.interfaces.trusted_submission_intake import TrustedIntakePreparation, TrustedSubmissionIntakeAdapter
from app.interfaces.external_services import ExternalServiceAdapterError
from app.modules.artifacts.trusted_intake import prepared_trusted_intake, TrustedArchiveInspector, prepare_bytes_with_intake
from app.modules.checkers.api.materialization import (
    PostSubmissionMaterialConsumer, PostSubmissionMaterializationResult,
    PostSubmissionMaterializationUnavailable, PostSubmissionMaterializationFailure,
    SubmissionMaterialEntry, MaterializationFacts, MaterializationAuthorityPort, PreparedMaterialization,
)
from app.modules.artifacts.post_submit_selection import (
    select_post_submission_material,
)
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchIntegrityError
from app.modules.artifacts.preparation import (
    ExternalMaterialFile,
    PostExternalMaterialGrantRequest,
)
from app.modules.artifacts.service import ArtifactStorageNamespaceError, ArtifactStorageNamespaceSpec
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveRejectedError,
    SubmissionArchiveLimits,
)
from app.modules.artifacts.submission_archive import (
    SealedSubmissionTree,
    exported_submission_tree,
)
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionResult,
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


class _MaterialView:
    """Revoke callback access independently of the private projection lifetime."""
    def __init__(
        self, tree: SealedSubmissionTree, *, preparation, prepared, workspace,
        execution: ExecuteFacts, materialization: MaterializationFacts, media_type: str,
    ) -> None:
        """Wrap the single ART-owned sealed tree without exposing its path."""
        self._tree = tree
        self._preparation, self._prepared, self._workspace = preparation, prepared, workspace
        self._execution, self._materialization = execution, materialization
        self._media_type = media_type
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

    @contextmanager
    def external_checker_grant(self, request: ExternalCheckerExecutionRequest):
        """Bind a POST service grant to actual current execution and ART ancestry."""
        self._require_open()
        checked = ExternalCheckerExecutionRequest.model_validate(request)
        identity = checked.identity
        if not isinstance(identity, PostSubmitExternalCheckerIdentity):
            raise ArtifactScratchIntegrityError("external POST request identity differs")
        execution, facts = self._execution, self._materialization
        source = execution.request
        lease = execution.lease
        reservation = lease.reservation
        if (
            identity.project_id != source.project_id
            or identity.task_id != source.task_id
            or identity.assignment_id != source.assignment_id
            or identity.submission_id != source.submission_id
            or identity.submission_version != source.submission_version
            or identity.evaluation_request_id != source.evaluation_request_id
            or identity.evaluation_request_digest != source.request_sha256
            or identity.evaluation_generation != source.evaluation_generation
            or identity.attempt_id != reservation.attempt_id
            or identity.result_id != reservation.result_id
            or identity.lease_id != lease.lease_id
            or identity.lease_generation != lease.lease_generation
            or identity.lease_expires_at != lease.expires_at
            or len(checked.materials) != 1
            or not isinstance(checked.materials[0], PostSubmitExternalCheckerMaterial)
        ):
            raise ArtifactScratchIntegrityError("external POST execution identity differs")
        material = checked.materials[0]
        expected = facts.material
        if (
            material.submission_id != expected.submission_id
            or material.submission_version != expected.submission_version
            or material.binding_id != expected.binding_id
            or material.content_id != expected.content_id
            or material.replica_id != expected.replica_id
            or material.content_sha256 != expected.content_sha256
            or material.byte_count != expected.byte_count
            or material.evidence_id != facts.evidence_id
            or material.verification_receipt_id != facts.verification_receipt_id
            or material.verification_job_id != facts.verification_job_id
            or material.verification_generation != facts.verification_generation
            or material.namespace_fingerprint != facts.namespace_fingerprint
            or material.semantic_manifest_sha256 != expected.semantic_manifest_sha256
        ):
            raise ArtifactScratchIntegrityError("external POST material identity differs")
        entries = self.entries
        directories = tuple(item.normalized_path for item in entries if item.entry_type == "directory")
        files = tuple(ExternalMaterialFile(
            normalized_path=item.normalized_path, byte_count=item.byte_count,
            sha256=item.sha256 or "", executable=bool(item.executable),
        ) for item in entries if item.entry_type == "file")
        lease_expires_at = identity.model_dump(mode="json")["lease_expires_at"]
        grant_request = PostExternalMaterialGrantRequest(
            request_digest=checked.request_digest,
            submission_id=str(identity.submission_id),
            submission_version=identity.submission_version,
            evaluation_request_id=str(identity.evaluation_request_id),
            evaluation_request_digest=identity.evaluation_request_digest,
            evaluation_generation=identity.evaluation_generation,
            attempt_id=str(identity.attempt_id), result_id=str(identity.result_id),
            lease_id=str(identity.lease_id), lease_generation=identity.lease_generation,
            lease_expires_at=lease_expires_at,
            binding_id=str(material.binding_id), content_id=str(material.content_id),
            replica_id=str(material.replica_id), content_sha256=material.content_sha256,
            byte_count=material.byte_count, evidence_id=str(material.evidence_id),
            verification_receipt_id=str(material.verification_receipt_id),
            verification_job_id=str(material.verification_job_id),
            verification_generation=material.verification_generation,
            namespace_fingerprint=material.namespace_fingerprint,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
            directories=directories, files=files,
        )
        with self._preparation.external_material_grant(
            self._prepared, self._workspace, grant_request
        ) as grant:
            yield ExternalCheckerMaterialGrant(
                grant_id=grant.grant_id,
                binding_digest=grant.binding_digest,
            )

    @property
    def external_checker_material(self) -> PostSubmitExternalCheckerMaterial:
        """Detach the exact verified POST lineage selected before byte access."""
        self._require_open()
        facts = self._materialization
        material = facts.material
        return PostSubmitExternalCheckerMaterial(
            role="submission_archive",
            submission_id=material.submission_id,
            submission_version=material.submission_version,
            binding_id=material.binding_id,
            content_id=material.content_id,
            replica_id=material.replica_id,
            content_sha256=material.content_sha256,
            byte_count=material.byte_count,
            media_type=self._media_type,
            evidence_id=facts.evidence_id,
            verification_receipt_id=facts.verification_receipt_id,
            verification_job_id=facts.verification_job_id,
            verification_generation=facts.verification_generation,
            namespace_fingerprint=facts.namespace_fingerprint,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
        )

    def __reduce__(self):
        """Prevent transfer of a process-local read capability."""
        raise TypeError("submission material view is process-local")


class _MaterialProcessor:
    """Keep async evaluation inside the shared projection and scratch lifetime."""
    def __init__(
        self, intake, inspection, request, consumer, *, preparation, prepared, limits,
        execution, materialization, media_type,
    ) -> None:
        """Bind one inspection, request and consumer for preparation-owned execution."""
        self._intake, self._inspection, self._limits = intake, inspection, limits
        self._request, self._consumer = request, consumer
        self._preparation, self._prepared = preparation, prepared
        self._execution, self._materialization = execution, materialization
        self._media_type = media_type
        self._aborted = False
        self._consumer_task: asyncio.Task[PostSubmissionExecutionResult] | None = None
        self._view: _MaterialView | None = None

    def abort(self) -> None:
        """Revoke reads and cancel the consumer before preparation drains cleanup."""
        self._aborted = True
        self._intake.abort()
        if self._view is not None:
            self._view.close()
        if self._consumer_task is not None:
            self._consumer_task.cancel()

    async def process(self, reader, workspace) -> PostSubmissionExecutionResult:
        """Project off-loop, validate callback output, and drain projection cleanup."""
        del reader
        projection = exported_submission_tree(self._intake.export, workspace,
                                             expected=self._inspection, limits=self._limits)
        # The preparation owner shields and drains this entire operation, including
        # projection entry, before it releases the reader or workspace.
        tree = await asyncio.to_thread(projection.__enter__)
        try:
            if self._aborted:
                raise asyncio.CancelledError
            self._view = _MaterialView(
                tree, preparation=self._preparation, prepared=self._prepared,
                workspace=workspace, execution=self._execution,
                materialization=self._materialization, media_type=self._media_type,
            )
            await self._intake.close()
            if self._aborted:
                raise asyncio.CancelledError
            self._consumer_task = asyncio.create_task(self._consumer.evaluate(self._request, self._view))
            result = validate_execution_result(await self._consumer_task)
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
        intake: TrustedSubmissionIntakeAdapter,
        archive_limits: SubmissionArchiveLimits,
        artifact_deadline_ms: int,
        authority: Callable[[AsyncSession], MaterializationAuthorityPort],
        current_execution: Callable[[AsyncSession], CurrentExecutionPort],
    ) -> None:
        """Require explicit owner ports, scratch service and material authority."""
        self._sessions, self._tasks, self._store = sessions, tasks, store
        self._namespace, self._preparation = namespace, preparation
        self._intake, self._authority = intake, authority
        self._archive_limits, self._artifact_deadline_ms = archive_limits, artifact_deadline_ms
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
                async with AsyncExitStack() as intake_cleanup:
                    pending_intake = await intake_cleanup.enter_async_context(prepared_trusted_intake(
                        self._intake, TrustedIntakePreparation(
                            phase="post_submit", policy_sha256=request.policy.policy_sha256,
                            limits=self._archive_limits, deadline_ms=self._artifact_deadline_ms,
                        ),
                    ))
                    prepared, intake = await prepare_bytes_with_intake(pending_intake,
                        self._preparation.prepare(
                            self._store.open(selected.provider_object_ref), media_type=selected.media_type,
                            expected_sha256=selected.sha256, expected_size=selected.byte_count,
                        ),
                    )
                    inspection = await prepared.inspect(TrustedArchiveInspector(intake, prepared.commitment),
                                                        on_cancel=intake.abort)
                    manifest = build_submission_manifest(inspection)
                    if manifest.sha256 != selected.semantic_manifest_sha256:
                        raise PostSubmissionMaterializationFailure("post_submit_material_manifest_mismatch")
                    materialization_facts = self._authority_facts(facts, selected)
                    evaluation = await self._preparation._process_prepared_submission(
                        prepared, _MaterialProcessor(
                            intake, inspection, request, consumer, limits=self._archive_limits,
                            preparation=self._preparation, prepared=prepared,
                            execution=facts, materialization=materialization_facts,
                            media_type=selected.media_type,
                        ),
                        reserved_bytes=manifest.total_expanded_bytes,
                        # ART's external grant adds one owned mount around the tree.
                        maximum_entries=manifest.entry_count + 1,
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
            ExternalServiceAdapterError,
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
