"""Source-shape rejection before artifact access, with a complete valid control."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples
from app.modules.projects.api.guide_documents import GuideDocumentUnavailable, GuideDocumentManifestRequest
from app.modules.projects.guide_compilation.document_scope import SqlAlchemyProjectGuideDocumentScope


def source_rows():
    project, guide_id, snapshot_id, setup_id, item_id, ingest_id = (uuid4() for _ in range(6))
    request = GuideDocumentManifestRequest(project_id=project, guide_id=guide_id,
        guide_source_snapshot_id=snapshot_id, project_setup_run_id=setup_id, setup_generation=1)
    examples = validate_task_examples([{"content": "Review a claim using the project guide."}])
    digest = task_examples_hash(examples)
    guide = SimpleNamespace(id=str(guide_id), project_id=str(project), version='v0.1',
        task_examples=[item.model_dump(mode="json") for item in examples], task_examples_hash=digest)
    snapshot = SimpleNamespace(id=str(snapshot_id), bundle_hash='sha256:'+'a'*64, captured_at=datetime.now(timezone.utc))
    snapshot.manifest_json = {"task_examples_hash": digest, "task_examples_count": 1}
    setup = SimpleNamespace(id=str(setup_id), setup_generation=1)
    item = SimpleNamespace(id=str(item_id), source_kind='document', ingestion_adapter='upload',
        media_type='application/pdf', item_order=0)
    ingest = SimpleNamespace(id=str(ingest_id), media_type='application/pdf', sha256='sha256:'+'b'*64, byte_count=42)
    return request, (guide, snapshot, setup), item, ingest


async def resolve(request, header, items, ingest):
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: header)),
        scalar=AsyncMock(side_effect=[1, False, ingest]),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: items)))
    return await SqlAlchemyProjectGuideDocumentScope(session).lock_manifest_source(request)


@pytest.mark.parametrize('fault,code', [('missing_items','guide_documents_incomplete'),
    ('unsupported_source','guide_document_format_unsupported'),
    ('missing_ingest','guide_documents_incomplete'),
    ('different_media','guide_document_identity_mismatch')])
async def test_incomplete_or_inconsistent_source_never_yields_document_lineage(fault, code):
    request, header, item, ingest = source_rows()
    control = await resolve(request, header, [item], ingest)
    assert len(control.documents) == 1
    assert str(control.documents[0].ingest_id) == ingest.id
    items = [item]
    if fault == 'missing_items':
        items = []
    elif fault == 'unsupported_source':
        item.source_kind = 'url_doc'
    elif fault == 'missing_ingest':
        ingest = None
    else:
        ingest.media_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    with pytest.raises(GuideDocumentUnavailable, match=code):
        await resolve(request, header, items, ingest)


async def test_cleanup_selection_rejects_invalid_retained_configuration_without_leaking_it(caplog):
    from app.modules.projects.guide_compilation.runtime_resources import pending_runtime_resource_cleanup
    from .helpers import runtime_configuration

    config = runtime_configuration()
    valid_id, invalid_id, mismatch_id = uuid4(), uuid4(), uuid4()
    marker = 'untrusted-retained-instructions-must-not-be-logged'
    rows = [SimpleNamespace(id=valid_id, guide_material_hash='sha256:'+'a'*64,
        runtime_configuration=config.model_dump(mode='json'), runtime_configuration_hash=config.sha256),
        SimpleNamespace(id=invalid_id, guide_material_hash='sha256:'+'b'*64,
            runtime_configuration={'instructions': marker}, runtime_configuration_hash=config.sha256),
        SimpleNamespace(id=mismatch_id, guide_material_hash='sha256:'+'c'*64,
            runtime_configuration=config.model_dump(mode='json'), runtime_configuration_hash='sha256:'+'d'*64)]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
    assert await pending_runtime_resource_cleanup(session) == ((valid_id, 'sha256:'+'a'*64, config),)
    assert marker not in caplog.text
    assert [record.attempt_id for record in caplog.records] == [str(invalid_id), str(mismatch_id)]


@pytest.mark.parametrize("fault", ["missing", "changed", "foreign_snapshot", "wrong_count"])
async def test_example_lineage_failure_prevents_issuing_a_document_grant(fault):
    request, header, item, ingest = source_rows()
    control = await resolve(request, header, [item], ingest)
    assert len(control.documents) == 1
    guide, snapshot, _setup = header
    if fault == "missing":
        guide.task_examples = None
    elif fault == "changed":
        guide.task_examples[0]["content"] = "Changed after snapshot capture"
    elif fault == "foreign_snapshot":
        snapshot.manifest_json["task_examples_hash"] = "sha256:" + "0" * 64
    else:
        snapshot.manifest_json["task_examples_count"] = 2
    with pytest.raises(GuideDocumentUnavailable, match="guide_task_examples_unavailable"):
        await resolve(request, header, [item], ingest)


@pytest.mark.parametrize("defect", ["digest", "document_id"])
async def test_art_manifest_rejects_inconsistent_resolved_identity_after_valid_control(defect):
    """Exercise ART's independent identity check after PROJECTS grants the lineage."""
    from app.modules.artifacts.guide_documents import SqlAlchemyGuideDocumentManifest
    from .helpers import context, ids
    material = context(ids()).material
    document = material.documents[0]
    request = GuideDocumentManifestRequest(project_id=material.project_id, guide_id=material.guide_id,
        guide_source_snapshot_id=material.source_snapshot_id, project_setup_run_id=material.setup_run_id,
        setup_generation=material.setup_generation)
    attempt = SimpleNamespace(id=str(document.put_attempt_id), sha256=document.sha256,
        byte_count=document.byte_count, media_type=document.media_type,
        storage_namespace_id=document.storage_namespace_id, namespace_fingerprint=document.namespace_fingerprint)
    replica = SimpleNamespace(id=str(document.replica_id), storage_namespace_id=document.storage_namespace_id,
        namespace_fingerprint=document.namespace_fingerprint)
    content = SimpleNamespace(id=str(document.content_id), sha256=document.sha256,
        byte_count=document.byte_count, media_type=document.media_type)
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(one_or_none=lambda: (attempt, replica, content))))
    scope = SimpleNamespace(lock_manifest_source=AsyncMock(return_value=material))
    port = SqlAlchemyGuideDocumentManifest(session, scope)
    assert await port.load(request) == material
    if defect == "digest":
        content.sha256 = "sha256:" + "0" * 64
    else:
        content.id = "not-a-document-uuid"
    with pytest.raises(GuideDocumentUnavailable, match="guide_document_identity_mismatch"):
        await port.load(request)
