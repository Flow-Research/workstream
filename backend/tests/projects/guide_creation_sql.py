"""Raw SQL creation graphs derived from a fully authorized, rolled-back control."""

import copy
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash

TABLES = (
    "audit_events", "guide_mutation_idempotency_records", "project_guides",
    "guide_source_snapshots", "guide_source_snapshot_items", "project_setup_runs",
)


async def capture_creation_graph(client, project_id, headers, monkeypatch):
    """Obtain exact valid rows, then roll them back before raw-SQL proof begins."""
    graph = {}
    original_commit = AsyncSession.commit

    async def capture(session):
        await session.flush()
        guides = (await session.execute(text("select * from project_guides"))).mappings().all()
        if not guides:
            return await original_commit(session)
        assert len(guides) == 1
        for table in TABLES:
            graph[table] = [dict(row) for row in (
                await session.execute(text(f"select * from {table}"))
            ).mappings()]
        event_ids = {guides[0]["last_authorization_decision_event_id"]}
        event_ids.update(row["authorization_decision_event_id"] for row in graph["guide_source_snapshots"])
        graph["audit_events"] = [row for row in graph["audit_events"] if row["id"] in event_ids]
        assert len(graph["audit_events"]) == 2
        await session.rollback()

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", capture)
        response = await client.post(
            f"/api/v1/projects/{project_id}/guides", headers=headers,
            json={"version": "raw-control", "task_examples": [{"content": "Review a claim."}],
                  "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}]},
        )
    assert response.status_code == 201, response.text
    assert set(graph) == set(TABLES)
    return graph


async def insert_graph(connection, graph):
    """Bypass product services and ORM writes while retaining every database guard."""
    for table in TABLES:
        for row in graph[table]:
            value = dict(row)
            if table == "guide_mutation_idempotency_records":
                value.update(status="pending", response_json=None, setup_run_id=None, committed_at=None)
            await connection.execute(text(
                f"insert into {table} select * from jsonb_populate_record(null::{table}, cast(:row as jsonb))"
            ), {"row": json.dumps(value, default=str)})
    for row in graph["guide_mutation_idempotency_records"]:
        await connection.execute(text("""
            update guide_mutation_idempotency_records target
            set status=source.status, response_json=source.response_json,
                setup_run_id=source.setup_run_id, committed_at=source.committed_at
            from jsonb_populate_record(null::guide_mutation_idempotency_records, cast(:row as jsonb)) source
            where target.id=source.id
        """), {"row": json.dumps(row, default=str)})


def malformed_graph(control, fault):
    graph = copy.deepcopy(control)
    if fault == "missing_source":
        graph["guide_mutation_idempotency_records"] = [row for row in graph["guide_mutation_idempotency_records"]
                                                     if row["action_id"] == "project.guide.create"]
        for table in ("guide_source_snapshots", "guide_source_snapshot_items", "project_setup_runs"):
            graph[table] = []
    elif fault == "cross_key":
        for row in graph["guide_mutation_idempotency_records"]:
            if row["action_id"] == "project.guide_source_snapshot.create":
                row["idempotency_key"] = uuid4()
    elif fault in {"setup_status", "setup_step", "setup_ready_at", "setup_celery"}:
        fields = {"setup_status": ("status", "queued"),
                  "setup_step": ("current_step", "queued"),
                  "setup_ready_at": ("documents_ready_at", "2026-09-11T00:00:00+00:00"),
                  "setup_celery": ("celery_task_id", str(uuid4()))}
        field, value = fields[fault]
        graph["project_setup_runs"][0][field] = value
    return graph


def second_source_graph(control):
    """Build another fully attributed set for the same guide, with fresh evidence."""
    graph = copy.deepcopy(control)
    graph["project_guides"] = []
    graph["guide_mutation_idempotency_records"] = [row for row in graph["guide_mutation_idempotency_records"]
                                                 if row["action_id"] == "project.guide_source_snapshot.create"]
    source = graph["guide_source_snapshots"][0]
    graph["audit_events"] = [row for row in graph["audit_events"] if row["id"] == source["authorization_decision_event_id"]]
    replacements = {str(row["id"]): str(uuid4()) for rows in graph.values() for row in rows}
    ledger = graph["guide_mutation_idempotency_records"][0]
    replacements[str(ledger["operation_id"])] = str(uuid4())
    replacements[str(ledger["idempotency_key"])] = str(uuid4())
    serialized = json.dumps(graph, default=str)
    for old, new in replacements.items():
        serialized = serialized.replace(old, new)
    graph = json.loads(serialized)
    source = graph["guide_source_snapshots"][0]
    ledger = graph["guide_mutation_idempotency_records"][0]
    setup = graph["project_setup_runs"][0]
    old_hash = source["bundle_hash"]
    new_hash = canonical_json_hash(source["manifest_json"])
    graph = json.loads(json.dumps(graph).replace(old_hash, new_hash))
    source = graph["guide_source_snapshots"][0]
    ledger = graph["guide_mutation_idempotency_records"][0]
    setup = graph["project_setup_runs"][0]
    setup["setup_generation"] = 2
    from app.modules.projects.guide_mutation_service import GuideMutationService
    from uuid import UUID
    resource = GuideMutationService._source_resource(
        UUID(source["project_id"]), UUID(source["guide_id"]), source["guide_version"],
        UUID(source["id"]), source["bundle_hash"], UUID(ledger["operation_id"]),
    )
    digest = canonical_json_hash(resource.model_dump(mode="json"))
    ledger["resource_context_digest"] = digest
    graph["audit_events"][0]["after_facts"]["resource_context_digest"] = digest
    return graph


async def install_predicate_mutant(connection, fault):
    definition = await connection.scalar(text(
        "select pg_get_functiondef('require_guide_document_creation_pair()'::regprocedure)"))
    if fault.startswith("setup_"):
        predicates = {
            "setup_status": "setup_row.status IS DISTINCT FROM 'awaiting_documents'",
            "setup_step": "setup_row.current_step IS DISTINCT FROM 'awaiting_documents'",
            "setup_ready_at": "setup_row.documents_ready_at IS NOT NULL",
            "setup_celery": "setup_row.celery_task_id IS NOT NULL",
        }
        anchor = "         OR " + predicates[fault] + "\n"
        assert definition.count(anchor) == 1
        definition = definition.replace(anchor, "")
    elif fault == "cross_key":
        old = "root_row.actor_profile_id,root_row.identity_link_id,root_row.project_id,root_row.idempotency_key"
        new = "root_row.actor_profile_id,root_row.identity_link_id,root_row.project_id"
        assert definition.count(old) == 1
        definition = definition.replace(old, new)
        old = "source_row.actor_profile_id,source_row.identity_link_id,source_row.project_id,source_row.idempotency_key"
        assert definition.count(old) == 1
        definition = definition.replace(old, "source_row.actor_profile_id,source_row.identity_link_id,source_row.project_id")
    else:
        anchor = "      IF guide_row.id IS NULL OR root_row.id IS NULL OR source_row.id IS NULL"
        assert definition.count(anchor) == 1
        condition = ("snapshot_row.id IS NULL AND source_row.id IS NULL AND setup_row.id IS NULL"
                     if fault == "missing_source" else
                     "(SELECT count(*) FROM guide_source_snapshots WHERE guide_id=guide_key) > 1")
        definition = definition.replace(anchor, f"      IF {condition} THEN RETURN NULL; END IF;\n" + anchor)
    await connection.execute(text(definition))
