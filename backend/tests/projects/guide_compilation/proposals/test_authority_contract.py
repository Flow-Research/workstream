"""Fail-closed proposal authority and caller-owned transaction contracts."""

from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.api import ActorKind
from app.modules.projects.api.guide_proposals import (
    GuideProposalApproval,
    GuideProposalCorrection,
    GuideProposalError,
    GuideProposalSelection,
    GuideProposalTarget,
)
from app.modules.projects.guide_compilation.proposal_authority import (
    proposal_resource_json,
    require_proposal_authority,
)
from app.modules.projects.guide_compilation.proposal_service import GuideProposalService
from app.core.hashing import canonical_json_hash
from .contract_support import authority_case, target_values


@pytest.mark.parametrize(
    "field,value",
    [
        ("actor_profile_id", uuid4()),
        ("identity_link_id", uuid4()),
        ("scope_project_id", uuid4()),
        ("action_id", "project.guide_compilation.correction.request"),
        ("permission_id", "other"),
        ("resource_context_digest", "sha256:" + "c" * 64),
        ("admin_role_grant_id", "not-a-uuid"),
        ("authorization_decision_event_id", "not-a-uuid"),
    ],
)
def test_authority_receipt_requires_each_exact_provenance_field(field, value):
    actor, _, facts, receipt = authority_case()
    require_proposal_authority(receipt, facts, actor, "project.effective_policy.manage")
    with pytest.raises(GuideProposalError, match="authority_unavailable"):
        require_proposal_authority(
            replace(receipt, **{field: value}), facts, actor, "project.effective_policy.manage"
        )


def test_authority_rejects_lookalike_receipts_and_service_actors():
    actor, _, facts, receipt = authority_case()
    for supplied, identity in (
        (SimpleNamespace(**asdict(receipt)), actor),
        (
            receipt,
            replace(
                actor, actor_kind=ActorKind.SERVICE, service_identity="workstream.project.setup"
            ),
        ),
    ):
        with pytest.raises(GuideProposalError, match="authority_unavailable"):
            require_proposal_authority(supplied, facts, identity, "project.effective_policy.manage")


def test_resource_encoding_binds_business_facts_and_excludes_only_transport_request():
    _, _, facts, _ = authority_case()
    resource = proposal_resource_json(facts)
    assert canonical_json_hash(resource) == facts.digest
    assert "request_id" not in resource["locator"]
    assert replace(facts, locator=replace(facts.locator, request_id=uuid4())).digest == facts.digest
    assert (
        replace(facts, locator=replace(facts.locator, operation_id=uuid4())).digest != facts.digest
    )
    assert replace(facts, output_digest="sha256:" + "c" * 64).digest != facts.digest


@pytest.mark.parametrize("operation", ["review", "approve", "correct"])
async def test_unconfigured_authority_denies_all_operations_before_product_access(operation):
    actor, target, _, _ = authority_case()
    session = SimpleNamespace(
        in_transaction=lambda: True,
        in_nested_transaction=lambda: False,
        new=(),
        dirty=(),
        deleted=(),
    )
    service = GuideProposalService(session)
    with pytest.raises(GuideProposalError, match="authority_unavailable"):
        if operation == "review":
            await service.review_package(
                GuideProposalSelection(
                    project_id=target.project_id,
                    guide_id=target.guide_id,
                    compilation_id=target.compilation_id,
                ),
                actor=actor,
                request_id=uuid4(),
            )
        elif operation == "approve":
            await service.approve(
                GuideProposalApproval(target=target, idempotency_key=uuid4()),
                actor=actor,
                request_id=uuid4(),
                material=None,
                pre_capabilities=None,
                post_capabilities=None,
                planner=None,
            )
        else:
            await service.request_correction(
                GuideProposalCorrection(
                    target=target,
                    idempotency_key=uuid4(),
                    reason="Inspect the source again.",
                ),
                actor=actor,
                request_id=uuid4(),
            )


@pytest.mark.parametrize(
    "patch",
    [
        {"in_transaction": lambda: False},
        {"in_nested_transaction": lambda: True},
        {"new": (object(),)},
        {"dirty": (object(),)},
        {"deleted": (object(),)},
    ],
)
async def test_proposal_owner_requires_clean_caller_root_transaction(patch):
    actor, target, _, _ = authority_case()
    session = SimpleNamespace(
        **(
            dict(
                in_transaction=lambda: True,
                in_nested_transaction=lambda: False,
                new=(),
                dirty=(),
                deleted=(),
            )
            | patch
        )
    )
    with pytest.raises(GuideProposalError, match="proposal_unavailable"):
        await GuideProposalService(session).request_correction(
            GuideProposalCorrection(
                target=target,
                idempotency_key=uuid4(),
                reason="Inspect the source again.",
            ),
            actor=actor,
            request_id=uuid4(),
        )


@pytest.mark.parametrize(
    "model,extra",
    [
        (GuideProposalApproval, {"approval_status": "approved"}),
        (GuideProposalCorrection, {"reason": "Inspect source.", "successor_setup_generation": 99}),
    ],
)
def test_manager_commands_reject_unknown_server_owned_fields(model, extra):
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Extra inputs"):
        model(target=GuideProposalTarget(**target_values()), idempotency_key=uuid4(), **extra)


def test_complete_proposal_read_requires_manager_content_permission():
    from app.modules.authorization.catalogue import (
        ACTION_BY_ID,
        ActionId,
        PermissionId,
        ActionAvailability,
    )
    from app.modules.authorization.policy import ADMIN_ROLE_PERMISSIONS
    from app.modules.authorization.schemas import AdminRole

    definition = ACTION_BY_ID[ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ]
    assert definition.permission_id is PermissionId.PROJECT_GUIDE_MANAGE
    assert definition.availability is ActionAvailability.ACTIVE
    assert definition.permission_id in ADMIN_ROLE_PERMISSIONS[AdminRole.PROJECT_MANAGER]
    for role in (AdminRole.OPERATOR, AdminRole.AUDIT_AUTHORITY):
        assert PermissionId.PROJECT_SETUP_DIAGNOSTIC_READ in ADMIN_ROLE_PERMISSIONS[role]
        assert definition.permission_id not in ADMIN_ROLE_PERMISSIONS[role]
