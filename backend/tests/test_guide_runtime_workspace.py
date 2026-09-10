"""Exact grant, provider staging and cleanup recovery without model/network calls."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import asyncio

import httpx2
from openai import NotFoundError
import pytest

from app.adapters.project_agents.openai_workspace import OpenAIGuideWorkspace, cleanup_owned_resources
from app.modules.projects.api.guide_documents import GuideRuntimeCapabilities, GuideRuntimeResource, OpenGuideDocument
from tests.projects.guide_compilation.helpers import context, ids, SOURCE_BYTES


def missing(*_args, **_kwargs):
    raise NotFoundError("missing", response=httpx2.Response(404, request=httpx2.Request("GET", "https://api.openai.com/resource")), body=None)


class Custody:
    """Scripted durable port that keeps intent and deletion acknowledgement distinct."""

    def __init__(self):
        self.intents = {}
        self.known = {}
        self.deleted = set()
        self.failed = set()
        self.uncertain = set()
        self.opened = set()
        self.reject_receipt = False

    async def begin_allocation(self, **values):
        identifier = uuid4()
        self.intents[identifier] = values
        return identifier

    async def record_allocated(self, identifier, provider_id):
        if self.reject_receipt:
            raise RuntimeError("receipt unavailable")
        self.known[identifier] = GuideRuntimeResource(allocation_id=identifier, provider_id=provider_id, **{key: value for key, value in self.intents[identifier].items()
                if key in GuideRuntimeResource.__dataclass_fields__})

    async def record_uncertain(self, identifier):
        self.uncertain.add(identifier)

    async def record_document_open(self, handle):
        self.opened.add(handle)

    async def cleanup_resources(self):
        return tuple(row for identifier, row in self.known.items() if identifier not in self.deleted)

    async def record_deleted(self, identifier):
        self.deleted.add(identifier)

    async def record_cleanup_failed(self, identifier):
        self.failed.add(identifier)


class Grant:
    def __init__(self, manifest):
        self.manifest = manifest
        self.closed = False
        self.denied = False
        self.calls = 0

    @asynccontextmanager
    async def open(self, handle):
        self.calls += 1
        if self.closed or self.denied:
            raise RuntimeError("grant unavailable")
        document = next(item for item in self.manifest.documents if self.manifest.handle_for(item) == handle)
        with BytesIO(SOURCE_BYTES) as reader:
            yield OpenGuideDocument(document, reader)

    async def close(self):
        self.closed = True


@pytest.fixture
def workspace():
    compilation = context(ids())
    grant, custody = Grant(compilation.material), Custody()
    client = SimpleNamespace(
        containers=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(id="cntr_owned", network_policy=SimpleNamespace(type="disabled"), expires_after=SimpleNamespace(anchor="last_active_at", minutes=compilation.runtime_configuration.container_expiry_minutes))),
            delete=AsyncMock(), retrieve=AsyncMock(side_effect=missing),
            files=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id="cfile_owned", container_id="cntr_owned", path="/mnt/data/guide.pdf"))),
        ),
        files=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(id="file-owned", created_at=1_800_000_000, expires_at=1_800_000_000 + compilation.runtime_configuration.file_expiry_seconds)),
            delete=AsyncMock(return_value=SimpleNamespace(id="file-owned", deleted=True)),
            retrieve=AsyncMock(side_effect=missing),
        ),
    )
    instance = OpenAIGuideWorkspace(client, compilation.runtime_configuration, compilation.material, GuideRuntimeCapabilities(documents=grant, resources=custody))
    return instance, client, grant, custody


@pytest.mark.asyncio
async def test_duplicate_opens_revalidate_grant_but_stage_once(workspace):
    instance, client, grant, custody = workspace
    await instance.start()
    handle = instance.manifest.handle_for(instance.manifest.documents[0])
    first, second = await asyncio.gather(instance.open_document(handle), instance.open_document(handle))
    assert first == second
    assert first["document_version_id"] == str(instance.manifest.documents[0].ingest_id)
    assert grant.calls == 2
    assert client.files.create.await_count == client.containers.files.create.await_count == 1
    assert custody.opened == {handle}
    grant.denied = True
    with pytest.raises(RuntimeError, match="grant unavailable"):
        await instance.open_document(handle)
    assert client.files.create.await_count == 1
    await instance.close()
    assert grant.closed and len(custody.deleted) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("handle", ["foreign", "s3://bucket/private.pdf", "../../guide.pdf"])
async def test_unknown_handle_has_no_source_or_provider_access(workspace, handle):
    instance, client, grant, custody = workspace
    await instance.start()
    with pytest.raises(RuntimeError, match="handle is unavailable"):
        await instance.open_document(handle)
    assert grant.calls == 0
    client.files.create.assert_not_awaited()
    assert not custody.opened
    await instance.close()


@pytest.mark.asyncio
async def test_grant_denial_never_uploads_document(workspace):
    instance, client, grant, custody = workspace
    await instance.start()
    grant.denied = True
    with pytest.raises(RuntimeError, match="grant unavailable"):
        await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    client.files.create.assert_not_awaited()
    client.containers.files.create.assert_not_awaited()
    assert not custody.opened
    await instance.close()


@pytest.mark.asyncio
async def test_unrecorded_returned_id_is_cleaned_without_creating_again(workspace):
    instance, client, grant, custody = workspace
    custody.reject_receipt = True
    with pytest.raises(RuntimeError, match="receipt unavailable"):
        await instance.start()
    assert len(custody.uncertain) == 1 and not custody.known
    await instance.close()
    client.containers.create.assert_awaited_once()
    client.containers.delete.assert_awaited_once_with("cntr_owned")
    assert len(custody.deleted) == 1 and grant.closed


@pytest.mark.asyncio
async def test_cleanup_recovers_attachment_after_container_acknowledgement(workspace):
    instance, client, _grant, custody = workspace
    await instance.start()
    await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    container = next(row for row in custody.known.values() if row.kind == "container")
    custody.deleted.add(container.allocation_id)
    await cleanup_owned_resources(client, custody)
    client.containers.delete.assert_not_awaited()
    client.containers.retrieve.assert_awaited_once_with("cntr_owned")
    client.files.delete.assert_awaited_once_with("file-owned")
    assert len(custody.deleted) == 3


@pytest.mark.asyncio
async def test_cleanup_requires_confirmed_absence_and_retries_exact_ids(workspace):
    instance, client, _grant, custody = workspace
    await instance.start()
    await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    client.containers.retrieve.side_effect = None
    client.containers.retrieve.return_value = SimpleNamespace(id="cntr_owned")
    await cleanup_owned_resources(client, custody)
    assert {custody.known[key].kind for key in custody.deleted} == {"file"}
    assert {custody.known[key].kind for key in custody.failed} == {"container", "attachment"}
    client.containers.retrieve.side_effect = missing
    await cleanup_owned_resources(client, custody)
    assert len(custody.deleted) == 3
    client.files.delete.assert_awaited_once_with("file-owned")
    assert client.containers.delete.await_count == 2


@pytest.mark.asyncio
async def test_unknown_allocation_is_never_discovered_or_deleted(workspace):
    _instance, client, _grant, custody = workspace
    identifier = await custody.begin_allocation(kind="container", document_handle=None, parent_provider_id=None, expires_at=datetime.now(timezone.utc) + timedelta(minutes=20))
    await custody.record_uncertain(identifier)
    await cleanup_owned_resources(client, custody)
    client.containers.delete.assert_not_awaited()
    client.containers.retrieve.assert_not_awaited()
    client.files.delete.assert_not_awaited()
    assert not custody.deleted


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("container_id", "cntr_foreign"), ("path", "/etc/passwd"), ("path", "/mnt/data/../private")])
async def test_attachment_scope_mismatch_never_becomes_document_evidence(workspace, field, value):
    instance, client, _grant, custody = workspace
    await instance.start()
    setattr(client.containers.files.create.return_value, field, value)
    with pytest.raises(RuntimeError, match="attachment is invalid"):
        await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    assert not custody.opened
    await instance.close()


@pytest.mark.asyncio
async def test_document_close_failure_does_not_replace_known_result(workspace):
    instance, client, grant, custody = workspace
    await instance.start()
    grant.close = AsyncMock(side_effect=RuntimeError("close unavailable"))
    await instance.close()
    grant.close.assert_awaited_once()
    client.containers.delete.assert_awaited_once_with("cntr_owned")
    assert custody.deleted == set(custody.known)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["container", "file"])
async def test_provider_must_confirm_requested_resource_expiry(workspace, target):
    instance, client, grant, custody = workspace
    if target == "container":
        client.containers.create.return_value.expires_after.minutes += 1
        with pytest.raises(RuntimeError, match="expiry was not confirmed"):
            await instance.start()
    else:
        await instance.start()
        client.files.create.return_value.expires_at = None
        with pytest.raises(RuntimeError, match="expiry was not confirmed"):
            await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    client.containers.files.create.assert_not_awaited()
    assert not custody.opened
    await instance.close()
    assert grant.closed
    assert custody.deleted == set(custody.known)


@pytest.mark.asyncio
async def test_cleanup_already_missing_provider_objects_confirms_owned_deletion(workspace):
    instance, client, _grant, custody = workspace
    await instance.start()
    await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    client.containers.delete.side_effect = missing
    client.files.delete.side_effect = missing
    await cleanup_owned_resources(client, custody)
    assert custody.deleted == set(custody.known)
    assert not custody.failed
    client.containers.delete.assert_awaited_once_with('cntr_owned')
    client.files.delete.assert_awaited_once_with('file-owned')
    client.containers.retrieve.assert_awaited_once_with('cntr_owned')
    client.files.retrieve.assert_awaited_once_with('file-owned')


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['wrong_id', 'not_deleted', 'still_present'])
async def test_file_cleanup_requires_exact_receipt_and_absence_before_persisting(workspace, fault):
    instance, client, _grant, custody = workspace
    await instance.start()
    await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    file = next(row for row in custody.known.values() if row.kind == 'file')
    if fault == 'wrong_id':
        client.files.delete.return_value.id = 'file-foreign'
    elif fault == 'not_deleted':
        client.files.delete.return_value.deleted = False
    else:
        client.files.retrieve.side_effect = None
        client.files.retrieve.return_value = SimpleNamespace(id='file-owned')
    await cleanup_owned_resources(client, custody)
    assert file.allocation_id in custody.failed
    assert file.allocation_id not in custody.deleted
    assert {row.kind for key, row in custody.known.items() if key in custody.deleted} == {'container', 'attachment'}
    client.files.delete.return_value = SimpleNamespace(id='file-owned', deleted=True)
    client.files.retrieve.side_effect = missing
    await cleanup_owned_resources(client, custody)
    assert custody.deleted == set(custody.known)
    assert client.files.delete.await_count == 2
    client.containers.delete.assert_awaited_once()


@pytest.mark.parametrize('fault', [None, 'provider', 'overflow', 'continuation', 'exhausted'])
async def test_sdk_model_turn_enforces_compaction_and_hosted_work_budget(monkeypatch, fault):
    from agents import Runner, OpenAIResponsesModel
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
    from app.interfaces.project_agents import ProjectAgentRuntimeError
    from tests.test_agent_runtime import _compile

    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-only')
    compilation = context(ids())
    config = compilation.runtime_configuration
    observed = []

    class Workspace:
        container_id = 'cntr_owned'
        async def start(self):
            pass
        async def close(self):
            pass

    monkeypatch.setattr('app.adapters.project_agents.openai_agent_sdk.OpenAIGuideWorkspace',
                        lambda *_: Workspace())

    async def response(self, instructions, supplied, settings, *args, **kwargs):
        observed.append((supplied, settings.extra_args))
        if fault == 'provider':
            raise RuntimeError('provider unavailable')
        count = config.maximum_hosted_tool_calls + 1 if fault == 'overflow' else 1
        return SimpleNamespace(output=[SimpleNamespace(type='code_interpreter_call')] * count)

    monkeypatch.setattr(OpenAIResponsesModel, 'get_response', response)

    async def run(agent, prompt, **kwargs):
        if fault == 'exhausted':
            agent.model.hosted_calls = config.maximum_hosted_tool_calls
        supplied = [{'type': 'message', 'content': 'old'}, {'type': 'compaction'},
                    {'type': 'message', 'content': 'current'}]
        await agent.model.get_response(agent.instructions, supplied, agent.model_settings,
            agent.tools, agent.output_type, [], None,
            previous_response_id='foreign' if fault == 'continuation' else None)
        assert agent.model.hosted_calls == 1
        from tests.projects.guide_compilation.helpers import result
        return SimpleNamespace(final_output=result())

    monkeypatch.setattr(Runner, 'run', run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)
    if fault is None:
        await _compile(runtime, compilation)
    else:
        with pytest.raises(ProjectAgentRuntimeError, match='project guide run failed'):
            await _compile(runtime, compilation)
    if fault in ('continuation', 'exhausted'):
        assert observed == []
    else:
        assert observed == [([{'type': 'compaction'}, {'type': 'message', 'content': 'current'}],
                             {'max_tool_calls': config.maximum_hosted_tool_calls})]


@pytest.mark.parametrize('failed', [False, True])
async def test_sdk_cleanup_uses_owned_receipts_without_inference_admission(monkeypatch, workspace, failed):
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime

    instance, client, grant, custody = workspace
    await instance.start()
    await instance.open_document(instance.manifest.handle_for(instance.manifest.documents[0]))
    if failed:
        client.files.delete.side_effect = RuntimeError('provider unavailable')
    configurations = []

    @asynccontextmanager
    async def open_client(**values):
        configurations.append(values)
        yield client

    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-only')
    monkeypatch.setattr('openai.AsyncOpenAI', open_client)
    runtime = OpenAIAgentSdkProjectGuideRuntime(instance.configuration)
    assert await runtime.cleanup_resources(custody) is (not failed)
    assert runtime._admission is None
    assert configurations == [{'max_retries': 0, 'timeout': instance.configuration.request_timeout_seconds}]
    assert bool(await custody.cleanup_resources()) is failed
    await grant.close()
