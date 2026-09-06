"""Active-guide fact composition and delegation, with controlled owner rows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.projects.authorization_reads import authorize_project_active_guide_read
from app.modules.projects.service import GuideActivationBlocked, PolicySetupBlocked
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.policy_read_fixtures import _PolicyReadRepository


def _validator() -> SimpleNamespace:
    """Record delegation without duplicating the composer's lineage predicates."""
    return SimpleNamespace(
        validate_source_snapshot_integrity=AsyncMock(),
        validate_activation_ready=Mock(),
    )


async def _read(repository: _PolicyReadRepository, authorization: Any, service: Any) -> Any:
    """Invoke real active-guide composition with separately controlled ports."""
    return await authorize_project_active_guide_read(
        authorization=authorization,
        repository=cast(Any, repository),
        project_service=service,
        project_id=repository.project_id,
    )


def _expected_binding_payload(repository: _PolicyReadRepository) -> list[dict[str, Any]]:
    """Declare each fixture row's binding fields without introspecting production."""
    return [
        {"type": "SimpleNamespace", "id": repository.guide.id, "status": "active"},
        {"type": "SimpleNamespace", "id": repository.snapshot.id,
         "bundle_hash": repository.snapshot.bundle_hash},
        {"type": "SimpleNamespace", "id": repository.source_items[0].id},
        {"type": "SimpleNamespace", "id": repository.sufficiency.id, "status": "passed",
         "source_snapshot_hash": repository.snapshot.bundle_hash},
        {"type": "SimpleNamespace", "id": repository.submission.id,
         "lifecycle_status": "approved", "source_snapshot_hash": repository.snapshot.bundle_hash,
         "policy_hash": repository.submission.policy_hash},
        {"type": "SimpleNamespace", "id": repository.effective.id,
         "lifecycle_status": "approved", "source_snapshot_hash": repository.snapshot.bundle_hash,
         "effective_policy_hash": repository.effective.effective_policy_hash},
        {"type": "SimpleNamespace", "id": repository.checker.id,
         "lifecycle_status": "compiled", "source_snapshot_hash": repository.snapshot.bundle_hash,
         "effective_policy_hash": repository.effective.effective_policy_hash,
         "compiled_bundle_hash": repository.checker.compiled_bundle_hash},
        {"type": "SimpleNamespace", "id": repository.post_submit.id,
         "lifecycle_status": "approved", "source_snapshot_hash": repository.snapshot.bundle_hash,
         "policy_hash": repository.post_submit.policy_hash,
         "effective_policy_hash": repository.effective.effective_policy_hash},
        {"type": "SimpleNamespace", "id": repository.review.id},
        {"type": "SimpleNamespace", "id": repository.revision.id},
    ]


@pytest.mark.asyncio
async def test_active_guide_read_binds_exact_bundle_facts() -> None:
    """Return exactly the rows whose complete facts were passed to authorization."""
    repository = _PolicyReadRepository()
    authorization = SimpleNamespace(require=AsyncMock())

    bundle = await _read(repository, authorization, _validator())

    for field, row in {
        "guide": repository.guide, "source_snapshot": repository.snapshot,
        "sufficiency_report": repository.sufficiency,
        "submission_artifact_policy": repository.submission,
        "effective_policy": repository.effective, "pre_submit_checker_policy": repository.checker,
        "post_submit_checker_policy": repository.post_submit,
        "review_policy": repository.review, "revision_policy": repository.revision,
    }.items():
        assert getattr(bundle, field) is row
    assert bundle.source_items == repository.source_items
    authorization.require.assert_awaited_once()
    action, context = authorization.require.await_args.args
    assert action is ActionId.PROJECT_ACTIVE_GUIDE_READ
    assert context.model_dump(mode="json", exclude={"policy_binding_digest"}) == {
        "resource_type": "project_active_guide_read",
        "resource_id": repository.guide.id,
        "scope_project_id": repository.project_id,
        "guide_id": repository.guide.id,
        "guide_version": "v1", "guide_status": "active",
        "project_exists": True, "project_status": "active",
        "guide_exists": True, "target_exists": True,
        "source_snapshot_id": repository.snapshot.id,
        "source_snapshot_hash": repository.snapshot.bundle_hash,
        "sufficiency_report_id": repository.sufficiency.id,
        "sufficiency_report_status": "passed",
        "submission_artifact_policy_id": repository.submission.id,
        "submission_artifact_policy_hash": repository.submission.policy_hash,
        "submission_artifact_policy_status": "approved",
        "effective_policy_id": repository.effective.id,
        "effective_policy_hash": repository.effective.effective_policy_hash,
        "effective_policy_status": "approved",
        "pre_submit_checker_policy_id": repository.checker.id,
        "pre_submit_checker_bundle_hash": repository.checker.compiled_bundle_hash,
        "pre_submit_checker_policy_status": "compiled",
        "post_submit_checker_policy_id": repository.post_submit.id,
        "post_submit_checker_policy_status": "approved",
        "review_policy_id": repository.review.id,
        "revision_policy_id": repository.revision.id,
    }


@pytest.mark.asyncio
async def test_active_guide_read_binds_exact_digest() -> None:
    """Require the digest of all selected fixture rows, not merely a hash prefix."""
    repository = _PolicyReadRepository()
    authorization = SimpleNamespace(require=AsyncMock())
    expected = canonical_json_hash(_expected_binding_payload(repository))

    await _read(repository, authorization, _validator())

    authorization.require.assert_awaited_once()
    assert authorization.require.await_args.args[1].policy_binding_digest == expected


@pytest.mark.asyncio
async def test_active_guide_read_validates_source() -> None:
    """Delegate the exact snapshot and persisted item tuple to source validation."""
    repository = _PolicyReadRepository()
    service = _validator()

    await _read(repository, SimpleNamespace(require=AsyncMock()), service)

    service.validate_source_snapshot_integrity.assert_awaited_once_with(
        repository.snapshot, GuideActivationBlocked, persisted_items=repository.source_items,
    )


@pytest.mark.asyncio
async def test_active_guide_read_validates_readiness() -> None:
    """Delegate exactly the non-compensation bundle, without payment prerequisites."""
    repository = _PolicyReadRepository()
    service = _validator()

    await _read(repository, SimpleNamespace(require=AsyncMock()), service)

    service.validate_activation_ready.assert_called_once_with(
        repository.guide, repository.snapshot, repository.sufficiency,
        repository.submission, repository.effective, repository.checker,
        repository.post_submit, repository.review, repository.revision, None,
        require_payment_policy=False,
    )


@pytest.mark.asyncio
async def test_active_guide_read_rejects_stale_post_submit_binding() -> None:
    """The composer itself rejects staleness; the fake validator cannot mask it."""
    repository = _PolicyReadRepository()
    repository.post_submit.pre_submit_checker_bundle_hash = f"sha256:{'f' * 64}"
    authorization = SimpleNamespace(require=AsyncMock())
    service = _validator()

    with pytest.raises(RuntimeError, match="missing active-guide authorization unexpectedly allowed"):
        await _read(repository, authorization, service)

    authorization.require.assert_awaited_once()
    context = authorization.require.await_args.args[1]
    assert context.target_exists is False
    assert context.policy_binding_digest is None
    service.validate_source_snapshot_integrity.assert_not_awaited()
    service.validate_activation_ready.assert_not_called()


@pytest.mark.asyncio
async def test_active_guide_read_conceals_validator_failure() -> None:
    """Map an actual readiness-port exception to an unavailable authorization target."""
    repository = _PolicyReadRepository()
    authorization = SimpleNamespace(require=AsyncMock())
    service = _validator()
    service.validate_activation_ready.side_effect = PolicySetupBlocked("invalid canonical policy")

    with pytest.raises(RuntimeError, match="missing active-guide authorization unexpectedly allowed"):
        await _read(repository, authorization, service)

    service.validate_activation_ready.assert_called_once()
    authorization.require.assert_awaited_once()
    context = authorization.require.await_args.args[1]
    assert context.target_exists is False
    assert context.policy_binding_digest is None


@pytest.mark.asyncio
async def test_active_guide_read_propagates_authorizer_exception() -> None:
    """Never return a valid bundle when the authorization port raises."""
    repository = _PolicyReadRepository()
    failure = RuntimeError("sentinel authorizer exception")
    authorization = SimpleNamespace(require=AsyncMock(side_effect=failure))

    with pytest.raises(RuntimeError) as raised:
        await _read(repository, authorization, _validator())

    assert raised.value is failure
    authorization.require.assert_awaited_once()
    assert authorization.require.await_args.args[0] is ActionId.PROJECT_ACTIVE_GUIDE_READ
    assert authorization.require.await_args.args[1].target_exists is True
