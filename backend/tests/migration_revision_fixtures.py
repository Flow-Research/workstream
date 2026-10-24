"""Checksum-bound historical revision inputs and guarded 0047 writers."""

import base64
from tests.trusted_intake_fixtures import LocalIntakeAdapter

from contextlib import asynccontextmanager
from datetime import timedelta
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import post_submission_materialization
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.artifacts import ArtifactStoreNamespaceClaim, ArtifactStoreNamespaceIdentity
from app.modules.artifacts.models import ArtifactStorageNamespace
from app.modules.artifacts.preparation import ArtifactPreparationService, ArtifactScratchManager
from app.modules.artifacts.service import ArtifactStorageNamespaceSpec
from app.modules.artifacts.api.submission_archive import (
    SubmissionArchiveLimits,
)
from app.modules.authorization.runtime import HumanAuthorizationContext
from app.modules.checkers.api import SelectedPostSubmissionEvaluationRequest
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.models import Submission, WorkstreamTask
from app.modules.tasks.schemas import AdmissionBackedSubmissionResponse
from tests.historical_submission_fixtures import (
    _restore_validated_snapshot_rows,
)
from tests.retained_material_fixtures import retained_archive_store
from tests.test_artifact_admission import _settings
from tests.test_checker_materialization import _limits


_REVISION_ARCHIVE = Path(__file__).with_name("fixtures") / "historical_revision_rows.json.gz"
_REVISION_ARCHIVE_SHA256 = "40b4c2bde917e6c8907da7d5462f6876a268952c449997af1ea93bffe6058420"
_REVISION_ARCHIVE_SCHEMA = "workstream.historical_revision_rows.v1"
_REVISION_ARCHIVE_SOURCE = "6fa9a9b557fa3ae22c16af67bca25dc868f67b38"


@lru_cache(maxsize=1)
def _historical_revision_snapshots() -> dict[str, dict[str, object]]:
    encoded = _REVISION_ARCHIVE.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == _REVISION_ARCHIVE_SHA256, (
        "historical revision row archive checksum mismatch"
    )
    body = json.loads(gzip.decompress(encoded))
    assert body["schema_version"] == _REVISION_ARCHIVE_SCHEMA
    assert body["source_revision"] == _REVISION_ARCHIVE_SOURCE
    return body["snapshots"]


async def _restore_historical_revision_rows(
    database_url: str, snapshot_name: str
) -> dict[str, object]:
    """Restore captured setup rows; this setup step is not a writer-guard proof."""
    snapshot = _historical_revision_snapshots()[snapshot_name]
    return await _restore_validated_snapshot_rows(
        database_url,
        snapshot,
        expected_revision=snapshot["revision"],
    )


class _HistoricalArtifactBootstrap:
    """Compose the current in-memory test store for an archived namespace."""

    def __init__(self, store, namespace: ArtifactStorageNamespaceSpec):
        self._store = store
        self.identity = store.identity
        descriptor = {
            key: value
            for key, value in namespace.namespace_descriptor.items()
            if key not in {"backend", "adapter", "provider_profile"}
        }
        self.namespace_identity = ArtifactStoreNamespaceIdentity(
            namespace.provider_profile,
            tuple(sorted((key, str(value)) for key, value in descriptor.items())),
        )
        self._claim = ArtifactStoreNamespaceClaim(
            self.identity, self.namespace_identity, namespace.namespace_fingerprint
        )

    def initialize_after_namespace_claim(self, claim):
        assert claim == self._claim
        return self._store

    def close(self):
        return None


@asynccontextmanager
async def historical_revision_source(tmp_path, database_url, monkeypatch, snapshot_name: str):
    """Load archived setup facts and current test-only ART composition."""
    seed = await _restore_historical_revision_rows(database_url, snapshot_name)
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    manager = ArtifactScratchManager(
        root=tmp_path / "historical-post-scratch",
        limits=_limits(reservation_ttl_seconds=300, total_deadline_seconds=180),
    )
    try:
        async with factory() as session:
            persisted = await session.get(ArtifactStorageNamespace, "primary")
            assert persisted is not None
            namespace = ArtifactStorageNamespaceSpec(
                persisted.backend,
                persisted.adapter,
                persisted.provider_profile,
                persisted.namespace_descriptor,
                persisted.namespace_fingerprint,
            )
        store = retained_archive_store(factory, namespace)
        data = base64.b64decode(seed["data_base64"])
        assert len(data) == seed["request"]["byte_count"]
        assert "sha256:" + hashlib.sha256(data).hexdigest() == seed["request"]["content_sha256"]
        async with factory() as session:
            provider_object_ref = await session.scalar(
                text(
                    "SELECT provider_object_ref FROM artifact_replicas "
                    "WHERE content_id=CAST(:content_id AS uuid)"
                ),
                {"content_id": seed["request"]["content_id"]},
            )
        assert provider_object_ref is not None
        store.objects[provider_object_ref] = data
        preparation = ArtifactPreparationService(manager)
        service = post_submission_materialization(
            sessions=factory,
            store=store,
            namespace=namespace,
            preparation=preparation,
            intake=LocalIntakeAdapter(), archive_limits=SubmissionArchiveLimits(), artifact_deadline_ms=180_000,
        )

        def archived_bootstrap(_settings, *, activation_guard):
            assert activation_guard is None
            return _HistoricalArtifactBootstrap(store, namespace)

        monkeypatch.setattr(
            "app.adapters.artifacts.create_artifact_store_bootstrap", archived_bootstrap
        )
        creation = seed["creation_request"]
        yield SimpleNamespace(
            factory=factory,
            engine=engine,
            request=SelectedPostSubmissionEvaluationRequest.model_validate_json(
                json.dumps(seed["request"])
            ),
            created=AdmissionBackedSubmissionResponse.model_validate_json(
                json.dumps(
                    {
                        name: seed["created"][name]
                        for name in AdmissionBackedSubmissionResponse.model_fields
                    }
                )
            ),
            actor_context=HumanAuthorizationContext.model_validate_json(
                json.dumps(seed["actor_context"])
            ),
            creation_request=SubmissionCreationRequest(
                admission_id=UUID(creation["admission_id"]),
                task_id=UUID(creation["task_id"]),
                assignment_id=UUID(creation["assignment_id"]),
                contributor_id=UUID(creation["contributor_id"]),
                predecessor_submission_id=(
                    UUID(creation["predecessor_submission_id"])
                    if creation["predecessor_submission_id"] is not None
                    else None
                ),
                summary=creation["summary"],
                contributor_attestation=creation["contributor_attestation"],
            ),
            source={"completion_event_id": UUID(seed["source"]["completion_event_id"])},
            data=data,
            settings=settings,
            namespace=namespace,
            store=store,
            service=service,
        )
    finally:
        manager.close()
        await engine.dispose()


async def assert_historical_revision_guards(factory, revision: str) -> None:
    """Confirm restore is closed before a real historical writer runs."""
    async with factory() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == revision
        assert (
            await session.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
                    "AND NOT t.tgisinternal AND t.tgenabled='D'"
                )
            )
            == 0
        )


async def insert_0047_preparation(session, *, manifest, candidate, audit_event_id):
    """Seed the old INSERT shape; current runtime never calls this test-only writer."""
    task = await session.get(WorkstreamTask, manifest.task_id)
    source_round = await session.scalar(select(func.count(Submission.id)).where(
        Submission.task_assignment_id == manifest.assignment_id,
        Submission.version <= manifest.submission_version,
    ))
    preparation_id = new_record_id()
    deadline = manifest.created_at + timedelta(hours=candidate.revision_deadline_hours)
    now = await session.scalar(select(func.clock_timestamp()))
    reason = (
        "revision_limit_reached" if source_round > candidate.max_revision_rounds or (
            candidate.target_max_revision_rounds is not None
            and source_round > candidate.target_max_revision_rounds
        ) else "revision_deadline_expired" if now >= deadline else
        "context_blocked" if candidate.target is None else None
    )
    outcome = "blocked" if reason else "kept"
    assert outcome == "blocked" or candidate.prior == candidate.target
    packet = {
        "domain": "workstream.task_revision_preparation.v1",
        "id": str(preparation_id), "routing_manifest_id": str(manifest.id),
        "predecessor_id": None, "sequence": 1,
        "requested_at": manifest.created_at.isoformat(), "deadline_at": deadline.isoformat(),
        "source_submission_version": manifest.submission_version,
        "next_revision_round": source_round, "max_revision_rounds": candidate.max_revision_rounds,
        "outcome": outcome, "blocked_reason": reason,
        "candidate": candidate.model_dump(mode="json"),
        "previous_task_lineage": {
            name: str(getattr(task, name)) if name.endswith("_id") else getattr(task, name)
            for name in TaskPolicyLineage.model_fields
        },
    }
    row = {
        "id": str(preparation_id), "project_id": manifest.project_id, "task_id": manifest.task_id,
        "assignment_id": manifest.assignment_id, "contributor_id": manifest.contributor_id,
        "submission_id": manifest.submission_id, "routing_manifest_id": str(manifest.id),
        "predecessor_id": None, "sequence": 1, "source_submission_version": manifest.submission_version,
        "next_revision_round": source_round, "max_revision_rounds": candidate.max_revision_rounds,
        "requested_at": manifest.created_at.isoformat(), "deadline_at": deadline.isoformat(),
        "outcome": outcome, "blocked_reason": reason, "packet": packet,
        "preparation_sha256": canonical_json_hash(packet),
        "authorization_decision_id": manifest.authorization_decision_id,
        "audit_event_id": str(audit_event_id),
    }
    columns = ",".join(row)
    result = (await session.execute(text(
        f"INSERT INTO public.task_revision_preparations ({columns}) "
        f"SELECT {columns} FROM jsonb_populate_record("
        "NULL::public.task_revision_preparations,CAST(:row AS jsonb)) RETURNING *"
    ), {"row": json.dumps(row)})).mappings().one()
    return SimpleNamespace(**result, remaining_microseconds=None, clock_observed_at=None)


async def retained_revision_rows(session, manifest_id, *, root_only=False):
    """Compare retained bytes plus table and physical row identities across ADD COLUMN."""
    selectors = {
        "revision_policies": "id=(SELECT s.locked_revision_policy_id FROM public.submissions s "
        "JOIN public.task_post_submit_routing_manifests m ON m.submission_id=s.id WHERE m.id=:id)",
        "workstream_tasks": "id=(SELECT task_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "task_assignments": "id=(SELECT assignment_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "submissions": "id=(SELECT submission_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "task_revision_preparations": "routing_manifest_id=:id",
        "task_post_submit_routing_manifests": "id=:id",
        "outbox_events": "idempotency_key='task.revision.expire:'||CAST(CAST(:id AS uuid) AS text)",
    }
    if root_only:
        selectors["task_revision_preparations"] += " AND predecessor_id IS NULL"
    result = {}
    for table, where in selectors.items():
        # 0049 backfills every submission and assignment by design, so those
        # rows keep their bytes minus its columns, not their physical version.
        rewritten = table in _ATTEMPT_OUTCOME_COLUMNS
        excluded = ("remaining_microseconds", "clock_observed_at", *_ATTEMPT_OUTCOME_COLUMNS.get(table, ()))
        values = await session.execute(text(
            f"SELECT (to_jsonb(row)-CAST(:excluded AS text[]))::text,tableoid::bigint,"
            f"{'NULL' if rewritten else 'xmin::text'} FROM public.{table} row WHERE {where}"
        ), {"id": manifest_id, "excluded": list(excluded)})
        result[table] = [tuple(row) for row in values]
        assert len(result[table]) == 1, table
    return result


_ATTEMPT_OUTCOME_COLUMNS = {
    "submissions": ("attempt_status", "status_reason", "decided_at", "updated_at"),
    "task_assignments": ("started_at", "updated_at"),
}
_PREDECESSOR_SHAPE = """
ALTER TABLE public.submissions ADD COLUMN attempt_status varchar(30) DEFAULT 'evaluation_pending' NOT NULL,
  ADD COLUMN status_reason varchar(40), ADD COLUMN decided_at timestamptz,
  ADD COLUMN updated_at timestamptz DEFAULT now() NOT NULL;
ALTER TABLE public.task_assignments ADD COLUMN started_at timestamptz,
  ADD COLUMN updated_at timestamptz DEFAULT now() NOT NULL;
CREATE TABLE public.checker_result_findings (
  id uuid PRIMARY KEY, checker_result_id uuid NOT NULL, checker_run_id uuid NOT NULL,
  task_id uuid NOT NULL, submission_id uuid NOT NULL, member_order integer NOT NULL,
  finding_order integer NOT NULL, check_id varchar(100) NOT NULL, code varchar(100) NOT NULL,
  level varchar(30) NOT NULL, path varchar(1000), line integer,
  created_at timestamptz DEFAULT now() NOT NULL)
"""
_ATTEMPT_OUTCOME_WRITERS = (
    "app.modules.tasks.post_submit_routing.outcome",
    "app.modules.tasks.accepted_effects",
    "app.modules.tasks.revision.expiry",
    "app.modules.tasks.revision.exhaustion",
)


async def enter_predecessor_owner_shape(execute, database_url, patch):
    """Let current owners build history on a pre-0049 schema, as its owners did.

    Predecessor owners stored no attempt outcomes, assignment starts or finding
    rows, so those writes are disabled and the ORM gets placeholder columns.
    ``leave_predecessor_owner_shape`` removes them before the real upgrade, so
    0049 runs against the genuine predecessor shape.
    """
    await execute(database_url, _PREDECESSOR_SHAPE)

    async def no_attempt_outcome(*_args, **_kwargs):
        return None

    for module in _ATTEMPT_OUTCOME_WRITERS:
        patch.setattr(f"{module}.record_attempt_outcome", no_attempt_outcome)


async def leave_predecessor_owner_shape(execute, database_url):
    """Remove the placeholders so the upgrade sees only predecessor DDL."""
    await execute(database_url, (
        "DROP TABLE public.checker_result_findings; "
        "ALTER TABLE public.submissions DROP COLUMN attempt_status, DROP COLUMN status_reason, "
        "DROP COLUMN decided_at, DROP COLUMN updated_at; "
        "ALTER TABLE public.task_assignments DROP COLUMN started_at, DROP COLUMN updated_at"
    ))
