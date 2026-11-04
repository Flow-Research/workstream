"""Reject altered predecessor reads without changing retained PostgreSQL evidence."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.projects.api.guide_proposals import GuideProposalCorrection
from app.modules.projects.guide_compilation.correction_feedback import load_correction_input
from app.modules.projects.guide_compilation.models import (
    ProjectGuideCompilation,
    ProjectGuideSetupFinalization,
)
from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError
from .pg_support import proposal_case, read_package
from .test_postgresql import correct


class AlteredPredecessorStorage:
    """Inject one bad read without modifying immutable database evidence."""

    def __init__(self, session, changes):
        """Retain the real session and one substituted read result."""
        self.session = session
        self.changes = changes

    async def get(self, model, key):
        """Hide only the selected finalization; preserve other exact lookups."""
        if model is ProjectGuideSetupFinalization and self.changes == {
            "missing_finalization": True
        }:
            return None
        return await self.session.get(model, key)

    async def scalar(self, statement):
        """Replace only the predecessor result returned by the actual query."""
        row = await self.session.scalar(statement)
        if isinstance(row, ProjectGuideCompilation):
            if self.changes is None:
                return None
            return SimpleNamespace(
                **{
                    **{column.key: getattr(row, column.key) for column in row.__table__.columns},
                    **self.changes,
                }
            )
        return row


async def test_correction_rejects_missing_or_altered_predecessor_custody(clean_postgres_database):
    """Every missing or substituted predecessor fact prevents context construction."""
    async with proposal_case(clean_postgres_database) as (_, factory, command, actor, grant):
        package = await read_package(factory, command, actor, grant)
        correction = await correct(
            factory,
            command,
            actor,
            grant,
            GuideProposalCorrection(
                target=package.target,
                idempotency_key=uuid4(),
                reason="Reconsider the existing source evidence.",
            ),
        )
        setup_id = UUID(str(correction.successor_setup_run_id))
        async with factory() as session:
            predecessor = await session.get(ProjectGuideCompilation, command.compilation_id)
            for changes in (
                None,
                {"missing_finalization": True},
                {"project_id": str(uuid4())},
                {"source_snapshot_id": str(uuid4())},
                {"setup_generation": predecessor.setup_generation + 1},
                {
                    "canonical_result": {
                        **predecessor.canonical_result,
                        "setup_notes": ["Substituted result."],
                    }
                },
                {
                    "component_hashes": {
                        **predecessor.component_hashes,
                        "pre_submit_hash": "sha256:" + "f" * 64,
                    }
                },
            ):
                with pytest.raises(GuideCompilationIntegrityError, match="correction predecessor"):
                    await load_correction_input(
                        AlteredPredecessorStorage(session, changes), setup_id
                    )

            intact = await load_correction_input(session, setup_id)
            assert intact.predecessor.model_dump(mode="json") == predecessor.canonical_result
