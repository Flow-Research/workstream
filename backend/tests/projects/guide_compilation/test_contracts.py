"""Canonical attempt and accepted-result contract behavior."""

from __future__ import annotations

import re
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.modules.authorization.api import (
    ProjectGuideCompilationRequestFacts,
    ProjectGuideCompilationRequestOrigin,
)
from app.modules.projects.guide_compilation.contracts import (
    AcceptedCompilationResult,
    accepted_compilation_result,
    validate_accepted_compilation_result,
)
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
from app.modules.projects.guide_compilation.repository import (
    GuideCompilationConcurrencyError,
    GuideCompilationRepository,
    GuideCompilationStorageError,
    _persistence_error,
)
from app.modules.projects.guide_compilation.validation import TERMINAL_FAILURE_CODES

from .helpers import context, identity, ids, persistence_facts, result, service_actor


def test_attempt_provider_key_is_deterministic_and_context_bound() -> None:
    """One exact logical attempt always produces one provider key."""
    values = ids()
    first = identity(context(values))
    assert first.provider_idempotency_key() == identity(context(values)).provider_idempotency_key()
    assert first.provider_idempotency_key() != first.model_copy(
        update={"instruction_version": "v2"}
    ).provider_idempotency_key()
    assert first.result_schema_version == "project_guide_check_specification.v1"
    assert not any("catalogue" in name for name in first.model_fields)


def test_accepted_result_commits_the_setup_only_component_schema() -> None:
    accepted = accepted_compilation_result(result())
    assert accepted.component_hashes.schema_version == "project_guide_check_specification_hashes.v1"
    assert set(accepted.component_hashes.model_fields) == {
        "schema_version",
        "sufficiency_hash",
        "artifact_policy_hash",
        "requirement_inventory_hash",
        "pre_submit_hash",
        "post_submit_hash",
    }


def test_accepted_result_rejects_component_or_full_hash_drift() -> None:
    """Durable provider output cannot be reconstructed with swapped hashes."""
    accepted = accepted_compilation_result(result())
    body = accepted.model_dump(mode="json")
    body["component_hashes"]["sufficiency_hash"] = "sha256:" + "b" * 64
    with pytest.raises(ValidationError, match="hashes are invalid"):
        AcceptedCompilationResult.model_validate(body)
    body = accepted.model_dump(mode="json")
    body["result_hash"] = "sha256:" + "b" * 64
    with pytest.raises(ValidationError, match="hashes are invalid"):
        AcceptedCompilationResult.model_validate(body)


def test_accepted_result_revalidates_against_fresh_context() -> None:
    """Stored output becomes unusable when its exact setup context drifts."""
    values = ids()
    original = context(values)
    attempt_identity = identity(original)
    accepted = accepted_compilation_result(result())
    assert validate_accepted_compilation_result(
        identity=attempt_identity, context=original, accepted=accepted
    ) == result()
    with pytest.raises(ValueError, match="context no longer matches"):
        validate_accepted_compilation_result(
            identity=attempt_identity,
            context=original.model_copy(update={"setup_generation": 2}),
            accepted=accepted,
        )


def test_terminal_failure_allowlist_matches_database_constraint() -> None:
    """Application and database accept the same closed terminal failure codes."""
    constraint = next(
        item
        for item in ProjectGuideCompilationAttempt.__table__.constraints
        if item.name and item.name.endswith("ck_compilation_attempt_state_shape")
    )
    definition = str(constraint.sqltext)
    allowlist = re.search(r"failure_code in \(([^)]+)\)", definition)
    assert allowlist is not None
    observed = set(re.findall(r"'([^']+)'", allowlist.group(1)))
    assert observed == TERMINAL_FAILURE_CODES


@pytest.mark.parametrize(
    ("constraint_name", "expected"),
    [
        ("uq_project_guide_compilation_predecessor", GuideCompilationConcurrencyError),
        ("uq_project_guide_compilation_root", GuideCompilationConcurrencyError),
        ("ck_project_guide_compilation_custody", GuideCompilationStorageError),
    ],
)
def test_database_failures_have_deterministic_domain_classification(
    constraint_name: str,
    expected: type[GuideCompilationConcurrencyError | GuideCompilationStorageError],
) -> None:
    """Known lineage races remain distinct from other storage failures."""
    original = RuntimeError("database failure")
    original.constraint_name = constraint_name  # type: ignore[attr-defined]
    error = IntegrityError("statement", {}, original)
    assert isinstance(_persistence_error(error), expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("constraint_name", "expected", "message"),
    [
        (
            "uq_compilation_request_setup_trigger",
            GuideCompilationConcurrencyError,
            "request won",
        ),
        ("unrelated_request_constraint", GuideCompilationStorageError, "before commit"),
    ],
)
async def test_request_insert_classifies_exact_natural_owner_constraint(
    constraint_name: str,
    expected: type[GuideCompilationConcurrencyError | GuideCompilationStorageError],
    message: str,
) -> None:
    """The request insert itself classifies only known replay-owner races."""
    values = ids()
    attempt_id = new_record_id()
    persisted = persistence_facts(values, attempt_id, identity(context(values)))
    request_fields = ProjectGuideCompilationRequestFacts.__dataclass_fields__
    facts = ProjectGuideCompilationRequestFacts(
        **{name: asdict(persisted)[name] for name in request_fields}
    )
    original = RuntimeError("injected request insert failure")
    original.constraint_name = constraint_name  # type: ignore[attr-defined]
    failure = IntegrityError("insert request", {}, original)
    session = SimpleNamespace(add=MagicMock(), flush=AsyncMock(side_effect=failure))

    with pytest.raises(expected, match=message) as raised:
        await GuideCompilationRepository(session).insert_request_operation(
            actor=service_actor(values),
            facts=facts,
            origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
            attempt=SimpleNamespace(id=attempt_id),
            authorization_decision_event_id=new_record_id(),
        )

    assert raised.value.__cause__ is failure
    session.add.assert_called_once()
