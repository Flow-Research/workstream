"""Approval validates selected revision context against the actual image publication."""

from types import SimpleNamespace

import pytest

from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import compile_external_checker_policies
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_compilation.proposal_approval import _compile_approval
from tests.checkers.external.test_policy import (
    _entry, _attachment, _request, _Registry,
    _model_configuration_schema, _model_profile, _Profiles,
)
from tests.checkers.external.test_trial_policy import _configuration

VERSION = "workstream_evaluation_context_version"
ROLES = "workstream_evaluation_context_roles"
SELECTED = ["predecessor_findings", "predecessor_submission_archive"]


def policy_case(method="model", *, registry_declared=True, selected=SELECTED):
    """Build one real publication and phase attachment, independent of setup output."""
    document = (
        _model_configuration_schema().document.copy()
        if method == "model"
        else {"type": "object", "properties": {key: {} for key in _configuration()}}
    )
    document["properties"] = dict(document["properties"])
    if registry_declared:
        document["properties"].update({VERSION: {"const": "v1"}, ROLES: {"type": "array"}})
    document["additionalProperties"] = True
    schema = ExternalCheckerSchema(
        schema_id="revision.config", schema_version="v1", document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    entry = _entry("acme.quality_review", "post_submit", schema)
    project_id = new_record_id()
    profile = _model_profile(project_id, entry)
    values = (
        {
            "model_profile_id": str(profile.profile_id),
            "model_profile_version": 1,
            "model_profile_digest": profile.profile_digest,
        }
        if method == "model"
        else _configuration()
    )
    if selected is not None:
        values.update({VERSION: "v1", ROLES: selected})
    return entry, _attachment(entry, "revision_image", values), project_id, _Profiles(profile)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["model", "trial"])
async def test_human_attachment_accepts_exact_declared_revision_context(method):
    entry, attachment, project_id, profiles = policy_case(method)
    _, post = await compile_external_checker_policies(
        _request(post=(attachment,)), _Registry((entry,)),
        project_id=project_id, profiles=profiles,
    )
    assert post.entries[0].configuration[ROLES] == SELECTED


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["incomplete", "unsupported_registry", "invalid_roles"])
async def test_approval_denies_false_context_selection(fault):
    entry, attachment, project_id, profiles = policy_case(
        registry_declared=fault != "unsupported_registry",
        selected=None if fault == "incomplete" else ["unknown"] if fault == "invalid_roles" else SELECTED,
    )
    if fault == "incomplete":
        attachment = attachment.model_copy(update={
            "configuration": attachment.configuration | {VERSION: "v1"},
        })
    with pytest.raises(ValueError, match="evaluation context"):
        await compile_external_checker_policies(
            _request(post=(attachment,)), _Registry((entry,)),
            project_id=project_id, profiles=profiles,
        )


@pytest.mark.asyncio
async def test_approval_checks_actual_registry_before_any_policy_write(monkeypatch):
    entry, attachment, project_id, profiles = policy_case(registry_declared=False)

    class NoWrites:
        def __getattr__(self, name):
            raise AssertionError(f"approval attempted persistence before validation: {name}")

    class PureProjectService:
        def __init__(self, session):
            assert isinstance(session, NoWrites)

        def _merge_effective_submission_artifact_policy(self, body):
            return body

    import app.modules.projects.guide_compilation.proposal_approval as approval
    monkeypatch.setattr(approval, "ProjectService", PureProjectService)
    locked = SimpleNamespace(view=SimpleNamespace(policy=SimpleNamespace(policy_body={})))
    command = SimpleNamespace(
        target=SimpleNamespace(project_id=project_id),
        pre_submit_attachments=(), post_submit_attachments=(attachment,),
    )
    with pytest.raises(GuideProposalError) as exc:
        await _compile_approval(
            NoWrites(), locked, command, new_record_id(), _Registry((entry,)), profiles,
        )
    assert exc.value.code == "approval_blocked"
