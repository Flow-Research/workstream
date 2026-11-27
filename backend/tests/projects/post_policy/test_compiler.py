"""POST projection consumes only the approval-locked policy bundle."""

import pytest

from app.modules.checkers.api.external_policy import (
    compile_external_checker_policy_bundle,
    validate_stored_external_checker_policies,
)
from app.modules.projects.post_policy.compiler import compile_saved_post_policy
from tests.checkers.external.test_policy import _entry, _attachment, _request, _Registry


@pytest.mark.asyncio
async def test_saved_post_policy_is_exact_approved_post_body():
    pre = _entry("acme.intake", "pre_submit")
    entry = _entry("acme.quality_review", "post_submit")
    locked = await compile_external_checker_policy_bundle(
        _request(pre=(_attachment(pre, "intake"),), post=(_attachment(entry, "project_quality"),)),
        _Registry((pre, entry)),
    )
    assert compile_saved_post_policy(policies=locked) == locked.post_submit
    assert compile_saved_post_policy(
        policies=validate_stored_external_checker_policies(locked.model_dump(mode="json"))
    ) == locked.post_submit


@pytest.mark.asyncio
async def test_saved_post_policy_rejects_changed_locked_bundle_digest():
    pre = _entry("acme.intake", "pre_submit")
    post = _entry("acme.quality_review", "post_submit")
    locked = await compile_external_checker_policy_bundle(
        _request(pre=(_attachment(pre, "intake"),), post=(_attachment(post, "quality"),)),
        _Registry((pre, post)),
    )
    changed = locked.model_dump(mode="json")
    changed["post_submit"]["policy_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError):
        compile_saved_post_policy(policies=validate_stored_external_checker_policies(changed))
