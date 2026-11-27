"""POST inspection must agree with accepted source semantics before export."""

from dataclasses import replace

import pytest

from app.modules.checkers.api.materialization import PostSubmissionMaterializationFailure
from tests.checkers.execution.support import material_execution
from tests.post_submit_materialization_helpers import material_fixture


async def test_inspected_source_semantics_must_match_accepted_manifest(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with material_fixture(tmp_path, isolated_database_env) as h:
        execution = await material_execution(h)
        inspect = h.inspector.inspect
        observed = []

        def changed_inspection(reader):
            actual = inspect(reader)
            changed = tuple(
                replace(entry, executable=False) if entry.normalized_path == "run.sh" else entry
                for entry in actual.entries
            )
            assert changed != actual.entries
            observed.append(actual)
            return replace(actual, entries=changed)

        def forbidden_export(*args, **kwargs):
            pytest.fail("manifest disagreement reached material export")

        class Consumer:
            async def evaluate(self, *args):
                pytest.fail("manifest disagreement reached the consumer")

        monkeypatch.setattr(h.inspector, "inspect", changed_inspection)
        monkeypatch.setattr(h.inspector, "_projected_tree", forbidden_export)
        with pytest.raises(PostSubmissionMaterializationFailure, match="manifest_mismatch"):
            await h.service.materialize(execution, Consumer())
        assert len(observed) == len(h.store.opens) == 1
        assert not h.preparation._active
        assert (await h.manager.usage()).reserved_bytes == 0
        assert list((h.scratch / "workspaces").iterdir()) == []
