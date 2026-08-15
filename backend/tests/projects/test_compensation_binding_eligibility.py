"""Focused PROJECTS owner-eligibility behavior for compensation bindings."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.projects.api import ProjectCompensationBindingUnavailable
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "active"])
async def test_non_retired_project_is_eligible(status: str) -> None:
    project_id = uuid4()
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=SimpleNamespace(id=str(project_id), status=status))
    )

    facts = await ProjectCompensationBindingEligibility(
        session
    ).lock_compensation_binding_project(project_id)

    assert facts.project_id == project_id
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("project", [None, SimpleNamespace(status="retired")])
async def test_absent_or_retired_project_is_concealed(project) -> None:
    session = SimpleNamespace(scalar=AsyncMock(return_value=project))

    with pytest.raises(ProjectCompensationBindingUnavailable):
        await ProjectCompensationBindingEligibility(
            session
        ).lock_compensation_binding_project(uuid4())

    session.scalar.assert_awaited_once()
