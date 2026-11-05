"""Forge location and evaluation retain only exact ART-issued input commitments."""

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.interfaces.external_checker_execution import (
    ExternalCheckerForgeLocatorResponse,
    ExternalCheckerIsolationReceipt,
)
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.forge_locator import (
    ExternalCheckerForgeLocator,
    FORGE_LOCATOR_STAGE_KEY,
    require_forge_locator_request,
)
from app.modules.checkers.models import CheckerRun
from app.modules.checkers.selected_post_submit_execution import SelectedPostSubmitProcessor
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor
from tests.checkers.external.support import post_registry_spec
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_checker_materialization import _limits

_CHANGE_URL = "https://github.com/acme/project/pull/17"
_CONFIGURATION = {
    "workstream_forge_facts_version": "v1",
    "forge": "github",
    "forge_origin": "https://github.com",
    "repository": "acme/project",
    "base_branch": "main",
}


def _schema(name, document):
    return ExternalCheckerSchema(
        schema_id=name, schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _forge_spec():
    spec = post_registry_spec()
    return type(spec).model_validate(spec.model_copy(update={
        "configuration_schema": _schema("forge_material_config", {
            "type": "object", "properties": {key: {} for key in _CONFIGURATION},
        }),
        "input_schema": _schema(spec.input_schema.schema_id, {
            "type": "object", "properties": {FORGE_LOCATOR_STAGE_KEY: {"const": "locate"}},
        }),
    }).model_dump())


async def _configuration(_factory, _project, _registry):
    return _CONFIGURATION


def _fixture_options():
    return dict(
        post_submit_registry_spec=_forge_spec(),
        post_submit_configuration_setup=_configuration,
        artifact_deadline_ms=240_000,
        scratch_limits=_limits(total_deadline_seconds=240, reservation_ttl_seconds=300),
    )


class _ScopedForge:
    forge_origin = "https://github.com"

    def __init__(self):
        self.reads = []

    def __call__(self, forge):
        assert forge == "github"
        return self

    def parse_change_url(self, value):
        assert value == _CHANGE_URL
        return "acme/project", 17

    async def fetch_change_facts(self, **selection):
        self.reads.append(selection)
        return SimpleNamespace(model_dump=lambda mode: {
            "schema_version": "workstream.forge_change_facts.v1", "change_url": _CHANGE_URL,
        })


class _GrantInspectingImage(ControlledSelectedExecution):
    """Controlled image responses, with actual request-bound ART grant files."""

    def __init__(self, scratch):
        super().__init__()
        self.scratch = scratch
        self.locator_requests, self.grants, self.manifests = [], [], []

    def _observe_grant(self, request, grant):
        workspace = self.scratch / "workspaces" / grant.grant_id
        manifest = json.loads((workspace / ".external-checker-grant.json").read_text())
        assert manifest["request_digest"] == request.request_digest
        assert manifest["visible_roles"] == ["submission_archive"]
        self.grants.append(grant)
        self.manifests.append(manifest)

    async def locate_forge_change(self, request, grant):
        require_forge_locator_request(request)
        self._observe_grant(request, grant)
        self.locator_requests.append(request)
        body = {
            "schema_version": "external_checker_forge_locator.v1",
            "request_digest": request.request_digest,
            "registry_entry_id": str(request.registry.registry_entry_id),
            "registry_entry_digest": request.registry.entry_digest,
            "phase": "post_submit", "change_url": _CHANGE_URL,
        }
        return ExternalCheckerForgeLocatorResponse(
            result=ExternalCheckerForgeLocator.model_validate_json(json.dumps({
                **body, "locator_digest": external_checker_json_hash(body),
            })),
            isolation=ExternalCheckerIsolationReceipt(
                repository="registry.example/workstream/checker",
                platform_manifest_digest=request.registry.image_digest,
                platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
                platform_manifest_byte_count=1024, operating_system="linux", architecture="amd64",
                config_image_id=request.registry.image_digest, runtime="runsc", isolation_mode="gvisor",
                sandbox_uid=65532, sandbox_gid=65532,
            ),
        )

    async def execute(self, request, grant):
        self._observe_grant(request, grant)
        return await super().execute(request, grant)


async def _stored_result(h):
    async with h.factory() as session:
        body = await session.scalar(select(CheckerRun.result_json).where(
            CheckerRun.submission_id == str(h.request.submission_id),
        ))
    assert body is not None
    return json.loads(body)


async def test_forge_receipt_survives_real_art_grants_and_executor_replay(
    tmp_path, isolated_database_env,
):
    async with material_fixture(tmp_path, isolated_database_env, **_fixture_options()) as h:
        image, forge = _GrantInspectingImage(h.scratch), _ScopedForge()
        executor = live_executor(h, selected_execution=image, forge_facts=forge)
        result = await executor.evaluate_post_submission(h.request)
        assert result.outcome == "completed"
        receipt = result.execution.external_members[0].forge_receipt
        assert receipt is not None
        assert len(image.locator_requests) == len(image.requests) == 1
        assert len(image.grants) == 2
        assert image.grants[0] != image.grants[1]
        assert image.grants[0].binding_digest != image.grants[1].binding_digest
        assert image.manifests[0]["request_digest"] != image.manifests[1]["request_digest"]
        assert receipt.locator.request_digest == image.locator_requests[0].request_digest
        assert receipt.locator_input_sha256 == image.locator_requests[0].input_sha256
        assert receipt.final_input_sha256 == image.requests[0].input_sha256
        assert receipt.facts_sha256 == external_checker_json_hash(image.requests[0].input["forge_facts"])
        assert receipt.materials == image.requests[0].materials
        assert forge.reads == [{"repository": "acme/project", "change_number": 17, "base_branch": "main"}]
        stored = await _stored_result(h)
        assert stored["execution"]["external_members"][0]["forge_receipt"] == receipt.model_dump(mode="json")
        # A fresh executor recovers the committed result rather than granting new reads.
        replay = await live_executor(h, selected_execution=image, forge_facts=forge).evaluate_post_submission(h.request)
        assert replay == result
        assert len(image.grants) == 2 and len(forge.reads) == 1
        assert await _stored_result(h) == stored
        assert not any((h.scratch / "workspaces").iterdir())


@pytest.mark.parametrize("field", ["facts", "locator_input", "final_input", "material", "locator"])
async def test_real_art_rejects_tampered_forge_receipt_before_retaining_completed_result(
    tmp_path, isolated_database_env, monkeypatch, field,
):
    original = SelectedPostSubmitProcessor.evaluate

    async def substituted(self, request, material):
        execution = await original(self, request, material)
        member = execution.external_members[0]
        receipt = member.forge_receipt
        if field == "material":
            altered = receipt.materials[0].model_copy(update={"semantic_manifest_sha256": "sha256:" + "f" * 64})
            receipt = receipt.model_copy(update={"materials": (altered,)})
        elif field == "locator":
            body = receipt.locator.model_dump(mode="json", exclude={"locator_digest"})
            body["request_digest"] = "sha256:" + "f" * 64
            locator = ExternalCheckerForgeLocator.model_validate_json(json.dumps({
                **body, "locator_digest": external_checker_json_hash(body),
            }))
            receipt = receipt.model_copy(update={"locator": locator})
        else:
            key = {"facts": "facts_sha256", "locator_input": "locator_input_sha256",
                   "final_input": "final_input_sha256"}[field]
            receipt = receipt.model_copy(update={key: "sha256:" + "f" * 64})
        return replace(execution, external_members=(replace(member, forge_receipt=receipt),))

    monkeypatch.setattr(SelectedPostSubmitProcessor, "evaluate", substituted)
    async with material_fixture(tmp_path, isolated_database_env, **_fixture_options()) as h:
        image, forge = _GrantInspectingImage(h.scratch), _ScopedForge()
        result = await live_executor(h, selected_execution=image, forge_facts=forge).evaluate_post_submission(h.request)
        assert len(image.grants) == 2  # Both real grant lifetimes finished before the substitution.
        assert result.outcome == "infrastructure_failed"
        assert result.execution is None
        assert result.infrastructure_failure_code == "material_unavailable"
        stored = await _stored_result(h)
        assert stored["execution"] is None
        assert not any((h.scratch / "workspaces").iterdir())
