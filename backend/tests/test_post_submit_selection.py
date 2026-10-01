"""Stored ownership, frozen context and independent-session selection proof."""

from dataclasses import asdict

import pytest
from sqlalchemy import event, text

from app.adapters.tasks import submitted_bundle_port
from app.core.identifiers import new_record_id
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest, SubmittedBundleUnavailable
from tests.checkers.post_submit.support import change_request
from tests.checkers.execution.support import material_execution
from app.modules.artifacts.post_submit_selection import select_post_submission_material
from tests.post_submit_materialization_helpers import material_fixture
from tests.test_post_submit_materialization import Consumer


async def test_task_projection_is_owner_qualified_and_exact(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        statements = []
        def observe(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(h.engine.sync_engine, "before_cursor_execute", observe)
        try:
            async with h.factory() as session:
                reader = submitted_bundle_port(session)
                with pytest.raises(SubmittedBundleUnavailable):
                    await reader.read(SubmittedBundleRequest(new_record_id(), h.request.task_id, h.request.submission_id))
                facts = await reader.read(SubmittedBundleRequest(h.request.project_id, h.request.task_id, h.request.submission_id))
            assert len(statements) == 2
            for statement in statements:
                assert "workstream_tasks.project_id =" in statement
                assert "submissions.task_id =" in statement and "submissions.id =" in statement
                assert "FOR UPDATE" not in statement
                assert "package_uri" not in statement and "policy_body" not in statement
                assert "worker_attestation" not in statement and "summary" not in statement
        finally:
            event.remove(h.engine.sync_engine, "before_cursor_execute", observe)
        assert facts.admission_id == h.created.admission_id
        assert facts.binding_id == h.created.artifact_binding_id
        assert facts.content_id == h.created.artifact_content_id
        async with h.factory() as session:
            row = (await session.execute(text("select * from submissions where id=:id"),
                                         {"id": str(h.created.submission_id)})).mappings().one()
        assert str(facts.assignment_id) == str(row["task_assignment_id"])
        assert str(facts.contributor_id) == str(row["contributor_id"])
        assert facts.contribution_policy_version_id == row["contribution_policy_version_id"]
        assert facts.predecessor_id is None and facts.predecessor_version is None
        mapping = {
            "guide_version": "locked_guide_version", "source_id": "locked_guide_source_snapshot_id",
            "source_hash": "locked_guide_source_snapshot_hash",
            "effective_policy_id": "locked_effective_project_submission_artifact_policy_id",
            "effective_policy_hash": "locked_effective_project_submission_artifact_policy_hash",
            "pre_policy_id": "locked_pre_submit_checker_policy_id", "pre_policy_hash": "locked_pre_submit_checker_bundle_hash",
            "post_policy_id": "locked_post_submit_checker_policy_id", "post_policy_version": "locked_post_submit_checker_policy_version",
            "post_policy_hash": "locked_post_submit_checker_policy_hash", "review_policy_id": "locked_review_policy_id",
            "review_generation": "locked_review_policy_generation", "review_hash": "locked_review_policy_hash",
            "revision_policy_id": "locked_revision_policy_id", "revision_generation": "locked_revision_policy_generation",
            "revision_hash": "locked_revision_policy_hash",
        }
        assert {key: str(value) for key, value in asdict(facts.context).items()} == {
            key: str(row[column]) for key, column in mapping.items()
        }


async def test_frozen_context_substitution_rejected_by_art_selection(tmp_path, isolated_database_env):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        for name in ("source_id", "effective_policy_id", "pre_policy_id", "post_policy_id", "review_policy_id", "revision_policy_id", "review_generation", "revision_hash"):
            value = (2 if name == "review_generation" else "sha256:" + "0" * 64 if name == "revision_hash" else new_record_id())
            expected = h.request.expected_context.model_copy(update={name: value})
            packet = h.request.structural_input.model_copy(update={
                "observed_context": h.request.structural_input.observed_context.model_copy(update={name: value}),
            })
            with pytest.raises(PostSubmissionMaterializationUnavailable, match="identity_mismatch"):
                await select_material(h, change_request(h.request, expected_context=expected, structural_input=packet))
        assert not h.store.opens and not h.preparation._active
        selected = await select_material(h, h.request)
        assert selected.submission.admission_id == h.created.admission_id


async def test_valid_foreign_lineage_mixes_deny_before_material_access(tmp_path, isolated_database_env, monkeypatch):
    async with material_fixture(tmp_path / "first", isolated_database_env) as first:
        # Share the configured store and fixed services, as two real projects do.
        async with material_fixture(
            tmp_path / "second", isolated_database_env,
            storage_settings=first.settings, provision_services=False,
        ) as second:
            fields = ("project_id", "task_id", "assignment_id", "submission_id", "binding_id", "content_id")
            assert all(getattr(first.request, key) != getattr(second.request, key) for key in fields)
            assert first.facts.contributor_id != second.facts.contributor_id
            assert first.created.admission_id != second.created.admission_id
            # Each untouched stored lineage must pass through real materialization.
            for own in (first, second):
                value = await own.service.materialize(await material_execution(own), Consumer(own.files))
                assert value.submission_id == own.created.submission_id
                own.store.opens.clear()
            def forbidden(*args, **kwargs):
                pytest.fail("foreign lineage reached provider, scratch, or consumer")
            for own, foreign in ((first, second), (second, first)):
                with monkeypatch.context() as patch:
                    patch.setattr(own.store, "open", forbidden)
                    patch.setattr(own.preparation, "prepare", forbidden)
                    mixtures = [{key: getattr(foreign.request, key)} for key in fields]
                    mixtures.extend((
                        {key: getattr(foreign.request, key) for key in fields if key != "project_id"},
                        {key: getattr(foreign.request, key) for key in ("binding_id", "content_id")},
                    ))
                    for mix in mixtures:
                        if "project_id" in mix:
                            # Keep duplicated project/policy facts schema-valid so
                            # rejection must come from persisted owner selection.
                            mix.update(policy=foreign.request.policy,
                                       expected_context=foreign.request.expected_context,
                                       structural_input=foreign.request.structural_input)
                        mixed = change_request(own.request, **mix)
                        with pytest.raises((PostSubmissionMaterializationUnavailable, SubmittedBundleUnavailable)):
                            await select_material(own, mixed)
                assert not own.store.opens
                assert not own.preparation._active
                assert list((own.scratch / "workspaces").iterdir()) == []


async def select_material(h, request):
    """Exercise ART selection itself, independently of earlier CHECKERS lease guards."""
    async with h.factory() as session:
        return await select_post_submission_material(
            session, tasks=submitted_bundle_port(session), request=request,
            namespace=h.namespace, store=h.store,
        )
