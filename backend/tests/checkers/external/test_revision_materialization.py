"""Approved revision inputs through real TASK/CHECKERS/ART and bounded scratch."""

import json

import pytest

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.interfaces.project_agents import CapabilityParameter, CheckSpecification
from app.modules.artifacts.preparation import HARD_MAXIMUM_ARTIFACT_BYTES
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import (
    EVALUATION_CONTEXT_ROLES_KEY as ROLES,
    EVALUATION_CONTEXT_VERSION_KEY as VERSION,
)
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor
from tests.checkers.external.support import post_registry_spec
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_dispatch.test_replacement_creation import (
    _create, _creation_request, _ready_replacement,
)
from tests.test_submission_predecessor_custody import _fixture_revision_context
from tests.test_checker_materialization import _limits


def _approved_context_proposal(monkeypatch, roles):
    """Script agent output before real compilation/PM approval; no stored-row edits."""
    from tests.projects.guide_activation import source_fixtures
    from tests.checkers.execution import completion_fixture

    original = source_fixtures._external_compilation_outcome
    document = {
        "type": "object",
        "properties": {VERSION: {"const": "v1"}, ROLES: {"type": "array", "items": {"type": "string"}}},
        "additionalProperties": False,
    }
    spec = post_registry_spec()
    spec = type(spec).model_validate(spec.model_copy(update={
        "configuration_schema": ExternalCheckerSchema(
            schema_id="revision_context_config", schema_version="v1", document=document,
            schema_sha256=external_checker_json_hash(document),
        ),
    }).model_dump())

    def outcome(*args, **kwargs):
        generated = original(*args, **kwargs)
        binding = generated.post_submit_bindings[0]
        configured = binding.model_copy(update={"parameters": (
            CapabilityParameter(name=VERSION, value="v1"),
            CapabilityParameter(name=ROLES, value=tuple(roles)),
        )})
        # Keep the unselected binding's original specification. Only the image
        # selecting predecessor material declares that exact runtime input.
        original_requirement = next(
            item for item in generated.requirements
            if item.requirement_id == binding.requirement_id
        )
        specification = original_requirement.check_specification.model_dump(mode="json")
        specification["inputs"].append({
            "input_id": "revision_context", "kind": "evaluation_context",
            "evaluation_context_roles": roles,
            "purpose": "Read exact approved predecessor evidence.",
        })
        specification["runtime_dependencies"].append({
            "dependency_id": "revision_context", "kind": "evaluation_context",
            "provisioning": "current_runner", "unavailable_code": "material_unavailable",
            "purpose": "Supply the exact selected predecessor evidence.",
        })
        specification["infrastructure_failures"].append({
            "code": "material_unavailable", "condition": "Selected predecessor evidence is absent.",
        })
        selected_requirement = original_requirement.model_copy(update={
            "check_specification": CheckSpecification.model_validate(specification),
        })
        # One context-aware image and one current-only binding to the same
        # declared image prove per-binding visibility inside one workspace.
        current_id = "project.z_current_only"
        return generated.model_copy(update={
            "requirements": (
                *(selected_requirement if item.requirement_id == binding.requirement_id else item
                  for item in generated.requirements),
                original_requirement.model_copy(update={"requirement_id": current_id}),
            ),
            "post_submit_bindings": (configured, binding.model_copy(update={"requirement_id": current_id})),
        })

    monkeypatch.setattr(source_fixtures, "_external_compilation_outcome", outcome)
    monkeypatch.setattr(completion_fixture, "post_registry_spec", lambda: spec)


class InspectingExecution(ControlledSelectedExecution):
    """Observe real ART manifests while returning a controlled image response."""

    def __init__(self, scratch):
        super().__init__()
        self.scratch, self.manifests = scratch, []

    async def execute(self, request, grant):
        path = self.scratch / "workspaces" / grant.grant_id / ".external-checker-grant.json"
        manifest = json.loads(path.read_text())
        assert manifest["request_digest"] == request.request_digest
        assert manifest["visible_roles"] == [item.role for item in request.materials]
        self.manifests.append(manifest)
        return await super().execute(request, grant)


class DiagnosticMaterialization:
    """Retain the internal denial cause when this positive journey unexpectedly fails."""

    def __init__(self, service):
        self.service = service

    async def materialize(self, facts, consumer):
        try:
            return await self.service.materialize(facts, consumer)
        except Exception as error:
            cause = error
            seen = {id(cause)}
            while cause.__cause__ is not None or cause.__context__ is not None:
                following = cause.__cause__ or cause.__context__
                if id(following) in seen:
                    break
                seen.add(id(following))
                cause = following
            raise AssertionError("expected successful revision materialization") from cause


@pytest.mark.parametrize("roles", [
    ("predecessor_findings",),
    ("predecessor_submission_archive",),
    ("predecessor_findings", "predecessor_submission_archive"),
])
async def test_revision_reads_exact_previous_material_with_per_binding_visibility(
    tmp_path, isolated_database_env, monkeypatch, roles,
):
    """Initial and revised evidence remain exact across two grants and replay."""
    _approved_context_proposal(monkeypatch, roles)
    from tests.test_s3_artifact_store import provision_minio_bucket

    await provision_minio_bucket.__wrapped__()
    # This composed journey includes two stored archives and two image grants.
    # Match the production aggregate allowance: two archive reservations plus
    # their bounded extraction workspace must coexist. The smaller one-archive
    # unit fixture has no room left for extraction after reserving a predecessor.
    # Dedicated capacity and deadline tests retain the rejection/cleanup proof.
    async with remediation_source(
        tmp_path, isolated_database_env, provider="minio",
        scratch_limits=_limits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=8, maximum_concurrency=4,
            total_deadline_seconds=60.0, reservation_ttl_seconds=120.0,
        ),
    ) as h:
        first_result, first_submission = h.result, h.created
        assert first_result.execution.external_members[0].input_receipt is not None
        assert first_result.execution.external_members[1].input_receipt is None
        await _fixture_revision_context(h)
        prepared, admission_id = await _ready_replacement(h, revision_archive(h.data))
        created = await _create(h, _creation_request(h, prepared, admission_id))
        async with h.factory() as session, session.begin():
            envelope = await evaluation_coordinator(session).read_reserved_evaluation(
                project_id=h.request.project_id, task_id=h.request.task_id,
                submission_id=created.submission_id, request_id=created.evaluation_request_id,
            )
        h.request = envelope.request
        h.service = DiagnosticMaterialization(h.service)
        adapter = InspectingExecution(h.scratch)
        executor = live_executor(h, selected_execution=adapter)
        h.store.opens.clear()
        completed = await executor.evaluate_post_submission(h.request)
        assert completed.outcome == "completed", completed.model_dump_json()
        assert len(h.store.opens) == 1 + int("predecessor_submission_archive" in roles)
        assert len(adapter.requests) == 2
        scoped, current_only = adapter.requests
        context = scoped.input["evaluation_context"]
        assert context["kind"] == "checker_remediation"
        assert context["predecessor"]["submission_id"] == str(first_submission.submission_id)
        assert context["source"]["preparation_id"] == str(h.revision_preparation_id)
        assert context["source"]["evaluation"]["result_digest"] == first_result.result_digest
        if "predecessor_findings" in roles:
            feedback = context["feedback"]
            assert feedback["source"]["result"]["result_digest"] == first_result.result_digest
            assert feedback["members"][0]["findings"][0]["code"] == "post_evidence_failed"
        else:
            assert context["feedback"] is None
        expected_roles = ["submission_archive"]
        if "predecessor_submission_archive" in roles:
            expected_roles.append("predecessor_submission_archive")
            assert scoped.materials[1].submission_id == first_submission.submission_id
        assert [item.role for item in scoped.materials] == expected_roles
        assert "evaluation_context" not in current_only.input
        assert len(current_only.materials) == 1
        assert adapter.manifests[1]["visible_roles"] == ["submission_archive"]
        assert adapter.manifests[1]["evaluation_context_sha256"] is None
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        async with h.factory() as session:
            retained = (await session.execute(text(
                "SELECT input_context_custody,public.checker_input_receipt_valid(r) AS valid "
                "FROM public.checker_runs r WHERE id=:id"
            ), {"id": completed.attempt_id})).one()
            assert retained.valid is True
            assert retained.input_context_custody["evaluation_context"] == context
            assert (retained.input_context_custody["predecessor"] is not None) == (
                "predecessor_submission_archive" in roles
            )
        if "predecessor_findings" in roles:
            # Validate the SQL predicate directly on detached candidate values:
            # immutable-row guards alone must not hide an incomplete witness.
            async with h.factory() as session:
                for replacement in ("'null'::jsonb", "to_jsonb(CAST('wrong' AS text))"):
                    valid = await session.scalar(text(
                        "SELECT public.checker_input_context_valid(jsonb_populate_record("
                        "NULL::public.checker_runs,jsonb_set(to_jsonb(r),"
                        "'{input_context_custody,evaluation_context,feedback,source,result,schema_version}',"
                        + replacement + "))) FROM public.checker_runs r WHERE id=:id"
                    ), {"id": completed.attempt_id})
                    assert valid is False
                missing = await session.scalar(text(
                    "SELECT public.checker_input_context_valid(jsonb_populate_record("
                    "NULL::public.checker_runs,to_jsonb(r) #- "
                    "'{input_context_custody,evaluation_context,feedback,source,result,schema_version}')) "
                    "FROM public.checker_runs r WHERE id=:id"
                ), {"id": completed.attempt_id})
                assert missing is False
        for expression in (
            "NULL",
            "jsonb_set(input_context_custody,'{evaluation_context,source,preparation_sha256}',to_jsonb(CAST(:wrong AS text)))",
        ):
            with pytest.raises(IntegrityError):
                async with h.factory() as session, session.begin():
                    await session.execute(text(
                        "UPDATE public.checker_runs SET input_context_custody=" + expression + " WHERE id=:id"
                    ), {"id": completed.attempt_id, "wrong": "sha256:" + "f" * 64})
        assert list((h.scratch / "workspaces").iterdir()) == []
        assert not h.preparation._active
        prior_calls, prior_opens = len(adapter.requests), len(h.store.opens)
        replay = await executor.evaluate_post_submission(h.request)
        assert replay == completed
        assert (len(adapter.requests), len(h.store.opens)) == (prior_calls, prior_opens)

        # A foreign request never acquires provider material or an image grant.
        from tests.checkers.post_submit.support import change_request
        from app.modules.checkers.api.execution import CheckerExecutionUnavailable

        with pytest.raises(CheckerExecutionUnavailable):
            await executor.evaluate_post_submission(change_request(h.request, assignment_id=new_record_id()))
        assert (len(adapter.requests), len(h.store.opens)) == (prior_calls, prior_opens)


async def test_cancellation_during_second_projection_drains_and_closes_every_role(
    tmp_path, monkeypatch
):
    """Cancellation aborts intake I/O and drains every entered trusted export."""
    import asyncio
    from contextlib import AsyncExitStack, contextmanager
    from io import BytesIO
    from threading import Event
    from zipfile import ZipFile

    from app.interfaces.trusted_submission_intake import TrustedIntakePreparation
    from app.modules.artifacts import post_submit_materialization
    from app.modules.artifacts.post_submit_materialization import _MaterialProcessor
    from app.modules.artifacts.preparation import (
        ArtifactPreparationLimits,
        ArtifactPreparationService,
        ArtifactScratchManager,
    )
    from app.modules.artifacts.submission_archive import (
        SubmissionArchiveInspector,
        SubmissionArchiveLimits,
    )
    from app.modules.artifacts.trusted_intake import prepared_trusted_intake

    archive = BytesIO()
    with ZipFile(archive, "w") as zipped:
        zipped.writestr("work.txt", b"original input")
    data = archive.getvalue()
    entered, release = Event(), Event()
    aborted = asyncio.Event()
    exits, trees, aborts, closes = [], [], [], []
    limits = SubmissionArchiveLimits()
    inspection = SubmissionArchiveInspector(limits).inspect(BytesIO(data))
    roles = ("submission_archive", "predecessor_submission_archive")

    original_export = post_submit_materialization.exported_submission_tree

    @contextmanager
    def observed_export(*args, **kwargs):
        workspace = args[1]
        with original_export(*args, **kwargs) as tree:
            trees.append(tree)
            try:
                yield tree
            finally:
                exits.append(workspace.name)

    monkeypatch.setattr(post_submit_materialization, "exported_submission_tree", observed_export)

    class Intake:
        def __init__(self, role):
            self.role = role

        def export(self, sink):
            for entry in inspection.entries:
                if entry.sha256 is not None:
                    sink(entry, b"original input")
            if self.role == "predecessor_submission_archive":
                entered.set()
                assert release.wait(10), "test failed to release trusted intake export"

        def abort(self):
            aborts.append(self.role)
            if set(aborts) == set(roles):
                aborted.set()

        async def close(self):
            closes.append(self.role)

    class Adapter:
        def __init__(self, session):
            self.session = session

        async def prepare(self, request):
            return self.session

    class NeverCalled:
        async def evaluate(self, request, view):
            pytest.fail("cancelled projection reached an evaluator")

    manager = ArtifactScratchManager(
        root=tmp_path / "scratch",
        limits=ArtifactPreparationLimits(
            aggregate_reserved_bytes=4 * HARD_MAXIMUM_ARTIFACT_BYTES,
            maximum_files=2,
            maximum_concurrency=2,
            minimum_free_bytes=0,
            stream_buffer_bytes=1024,
            maximum_source_bytes=1024,
            maximum_workspace_entries=16,
        ),
    )
    preparation = ArtifactPreparationService(manager)

    async def stream():
        yield data

    current = await preparation.prepare(stream(), media_type="application/zip")
    predecessor = await preparation.prepare(stream(), media_type="application/zip")
    sources = tuple(zip(roles, (current, predecessor), strict=True))
    sessions = {role: Intake(role) for role in roles}
    request = TrustedIntakePreparation(
        phase="post_submit",
        policy_sha256="sha256:" + "1" * 64,
        limits=limits,
        deadline_ms=10_000,
    )

    try:
        async with AsyncExitStack() as intake_cleanup:
            intakes = {}
            for role in roles:
                pending = await intake_cleanup.enter_async_context(
                    prepared_trusted_intake(Adapter(sessions[role]), request)
                )
                intakes[role] = await pending
            processor = _MaterialProcessor(
                intakes,
                dict.fromkeys(roles, inspection),
                None,
                NeverCalled(),
                limits=limits,
                preparation=preparation,
                sources=sources,
                execution=None,
                materialization=None,
                media_types={},
            )
            operation = asyncio.create_task(
                preparation._process_prepared_post_submission(
                    sources,
                    processor,
                    reserved_bytes=inspection.total_expanded_bytes * len(roles),
                    maximum_entries=inspection.entry_count * len(roles) + len(roles) + 2,
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 10)
                operation.cancel()
                await asyncio.wait_for(aborted.wait(), 1)
                operation.cancel()
                await asyncio.sleep(0)
                assert not operation.done()
                assert exits == []
                assert closes == []
            finally:
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(operation, 10)
            assert exits == list(reversed(roles))
            assert aborts == list(roles)
        assert closes == list(reversed(roles))
        for tree in trees:
            with pytest.raises(RuntimeError):
                tree.read_file("work.txt", maximum_bytes=100)
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        await current.close()
        await predecessor.close()
        manager.close()
