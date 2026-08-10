"""Canonical attempt and accepted-result contract behavior."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.projects.guide_compilation.contracts import (
    AcceptedCompilationResult,
    accepted_compilation_result,
    validate_accepted_compilation_result,
)

from .helpers import context, identity, ids, result


def test_attempt_provider_key_is_deterministic_and_context_bound() -> None:
    """One exact logical attempt always produces one provider key."""
    values = ids()
    first = identity(context(values))
    assert first.provider_idempotency_key() == identity(context(values)).provider_idempotency_key()
    assert first.provider_idempotency_key() != first.model_copy(
        update={"instruction_version": "v2"}
    ).provider_idempotency_key()


def test_accepted_result_rejects_component_or_full_hash_drift() -> None:
    """Durable provider output cannot be reconstructed with swapped hashes."""
    accepted = accepted_compilation_result(result())
    body = accepted.model_dump(mode="json")
    body["component_hashes"]["sufficiency_hash"] = "sha256:" + "b" * 64
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
