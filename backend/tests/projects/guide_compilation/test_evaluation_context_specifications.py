"""Setup declares only exact revision material already supported by selected POST."""

import pytest

from app.core.hashing import canonical_json_hash
from app.interfaces.project_agents import (
    CheckInput,
    CheckSpecification,
    require_complete_generated_specifications,
    CapabilityParameter,
    validate_post_submission_bindings,
)
from app.modules.checkers.api.external import ExternalCheckerSchema, external_checker_json_hash
from app.modules.checkers.api.external_policy import compile_external_checker_policies
from tests.checkers.external.support import capability_projection
from tests.checkers.external.test_policy import (
    _entry,
    _proposal,
    _Registry,
    _model_proposal,
    _model_configuration_schema,
    _model_profile,
    _Profiles,
)
from tests.checkers.external.test_trial_policy import trial_specification, _configuration
from tests.projects.guide_compilation.helpers import context, ids, valid_specification
from tests.projects.guide_compilation.test_check_specifications import (
    _requirement,
    _with_requirement,
)

VERSION = "workstream_evaluation_context_version"
ROLES = "workstream_evaluation_context_roles"
SELECTED = ["predecessor_findings", "predecessor_submission_archive"]


def specification(method="model", roles=SELECTED):
    base = (
        _model_proposal().requirements[-1].check_specification
        if method == "model"
        else trial_specification()
    )
    body = base.model_dump(mode="json")
    body["inputs"].append(
        {
            "input_id": "revision_material",
            "kind": "evaluation_context",
            "evaluation_context_roles": roles,
            "purpose": "Compare against the exact predecessor evidence.",
        }
    )
    body["runtime_dependencies"].append(
        {
            "dependency_id": "revision_material",
            "kind": "evaluation_context",
            "provisioning": "current_runner",
            "unavailable_code": "material_unavailable",
            "purpose": "Supply approved predecessor evidence.",
        }
    )
    body["infrastructure_failures"].append(
        {
            "code": "material_unavailable",
            "condition": "Approved evidence is unavailable.",
        }
    )
    return CheckSpecification.model_validate(body)


@pytest.mark.parametrize("method", ["model", "trial"])
def test_exact_context_admits_post_model_and_trial_handoffs(method):
    spec = specification(method)
    requirement = _requirement(disposition="supported_post_submit", check_specification=spec)
    require_complete_generated_specifications(context(ids()), _with_requirement(requirement))


@pytest.mark.parametrize("roles", [None, ["unknown"], [False], SELECTED[::-1], SELECTED * 2])
def test_exact_context_roles_cannot_be_absent_unknown_or_noncanonical(roles):
    with pytest.raises(ValueError):
        specification(roles=roles)


def test_context_roles_belong_only_to_one_exact_input_and_keep_retained_hashes():
    retained = {"input_id": "package", "kind": "package", "purpose": "Read the package."}
    decoded = CheckInput.model_validate(retained)
    assert decoded.model_dump(mode="json") == retained
    assert canonical_json_hash(decoded.model_dump(mode="json")) == canonical_json_hash(retained)
    with pytest.raises(ValueError, match="only on that kind"):
        CheckInput.model_validate(retained | {"evaluation_context_roles": []})
    body = specification().model_dump(mode="json")
    body["inputs"].append(body["inputs"][-1] | {"input_id": "duplicate"})
    with pytest.raises(ValueError, match="one exact"):
        CheckSpecification.model_validate(body)


@pytest.mark.parametrize("missing", ["inputs", "runtime_dependencies"])
def test_context_input_and_dependency_are_symmetric(missing):
    body = specification().model_dump(mode="json")
    body[missing].pop()
    with pytest.raises(ValueError, match="requires"):
        CheckSpecification.model_validate(body)


def test_context_is_post_background_only_and_broad_context_stays_unavailable():
    body = specification("trial").model_dump(mode="json")
    body["execution_mode"] = "bounded_pre_submit"
    with pytest.raises(ValueError, match="post-submit background"):
        CheckSpecification.model_validate(body)
    spec = specification("trial")
    requirement = _requirement(disposition="pre_submit_capability_gap", check_specification=spec)
    with pytest.raises(ValueError, match="post-submit background"):
        require_complete_generated_specifications(context(ids()), _with_requirement(requirement))
    body = valid_specification().model_dump(mode="json")
    body["execution_mode"] = "background"
    body["inputs"].append(
        {"input_id": "task", "kind": "task_context", "purpose": "Read task prose."}
    )
    body["runtime_dependencies"].append(
        {
            "dependency_id": "task",
            "kind": "task_context",
            "provisioning": "runtime_gap",
            "purpose": "Unavailable broad prose.",
            "unavailable_code": "material_unavailable",
        }
    )
    body["infrastructure_failures"].append(
        {"code": "material_unavailable", "condition": "No prose."}
    )
    requirement = _requirement(disposition="supported_post_submit", check_specification=body)
    with pytest.raises(ValueError, match="unavailable runtime"):
        require_complete_generated_specifications(context(ids()), _with_requirement(requirement))


def policy_case(method="model", *, declared=True, selected=SELECTED, registry_declared=True):
    """Use actual model/trial selectors and the actual registry/profile validators."""
    from app.core.identifiers import new_record_id

    proposal = _proposal()
    spec = specification(method) if declared else None
    req = proposal.requirements[-1].model_copy(update={"check_specification": spec})
    document = (
        _model_configuration_schema().document.copy()
        if method == "model"
        else {"type": "object", "properties": {key: {} for key in _configuration()}}
    )
    document["properties"] = dict(document["properties"])
    if registry_declared:
        document["properties"].update({VERSION: {"const": "v1"}, ROLES: {"type": "array"}})
    # Keep undeclared-selector denial in the canonical validator observable even
    # where a registry's ordinary schema allows extra configuration members.
    document["additionalProperties"] = True
    schema = ExternalCheckerSchema(
        schema_id="revision.config",
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    pre = _entry("acme.safe_archive", "pre_submit")
    post = _entry("acme.quality_review", "post_submit", schema)
    project_id = new_record_id()
    profile = _model_profile(project_id, post)
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
    binding = proposal.post_submit_bindings[0].model_copy(
        update={
            "parameters": tuple(
                CapabilityParameter(name=key, value=value) for key, value in values.items()
            ),
        }
    )
    proposal = proposal.model_copy(
        update={"requirements": (proposal.requirements[0], req), "post_submit_bindings": (binding,)}
    )
    return proposal, pre, post, project_id, _Profiles(profile)


@pytest.mark.parametrize("method", ["model", "trial"])
async def test_proposal_and_actual_approval_registry_accept_exact_revision_bindings(method):
    proposal, pre, post, project_id, profiles = policy_case(method)
    assert validate_post_submission_bindings(proposal, capability_projection(pre, post)) == {
        "quality_review"
    }
    _, policy = await compile_external_checker_policies(
        proposal, _Registry((pre, post)), project_id=project_id, profiles=profiles
    )
    assert policy.entries[0].configuration[ROLES] == SELECTED


@pytest.mark.parametrize("fault", ["undeclared", "unselected", "mismatch", "unsupported_registry"])
async def test_proposal_and_approval_independently_reject_false_context_bindings(fault):
    proposal, pre, post, project_id, profiles = policy_case(
        declared=fault != "undeclared",
        selected=None
        if fault == "unselected"
        else SELECTED[:1]
        if fault == "mismatch"
        else SELECTED,
        registry_declared=fault != "unsupported_registry",
    )
    for operation in ("proposal", "approval"):
        with pytest.raises(ValueError, match="evaluation context"):
            if operation == "proposal":
                validate_post_submission_bindings(proposal, capability_projection(pre, post))
            else:
                await compile_external_checker_policies(
                    proposal, _Registry((pre, post)), project_id=project_id, profiles=profiles
                )


async def test_approval_rechecks_actual_registry_before_any_policy_write(monkeypatch):
    """A good proposal projection cannot bless an unsupported actual publication."""
    from types import SimpleNamespace

    from app.core.identifiers import new_record_id
    from app.modules.projects.guide_compilation.proposal_approval import _compile_approval
    from app.modules.projects.guide_compilation.request_inputs import CompilationRequestInputs
    from app.modules.projects.service import WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY

    proposal, pre, post, project_id, profiles = policy_case()
    projection = capability_projection(pre, post)
    compilation_context = context(ids(), checker_capabilities=projection)

    # The original material loader is independently covered. Keep this proof on
    # the approval compiler's transition from valid projection to actual entry.
    async def context_for_setup(self, session, setup):
        return compilation_context

    monkeypatch.setattr(CompilationRequestInputs, "context_for_setup", context_for_setup)
    unsupported = _entry("acme.quality_review", "post_submit")

    class NoWrites:
        def __getattr__(self, name):
            raise AssertionError(f"approval attempted persistence before validation: {name}")

    locked = SimpleNamespace(
        result=proposal,
        view=SimpleNamespace(
            attempt=SimpleNamespace(
                runtime_configuration=compilation_context.runtime_configuration
            ),
            setup=object(),
            policy=SimpleNamespace(policy_body=WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY),
        ),
    )
    command = SimpleNamespace(target=SimpleNamespace(project_id=project_id))
    with pytest.raises(ValueError, match="does not declare evaluation context"):
        await _compile_approval(
            NoWrites(),
            locked,
            command,
            new_record_id(),
            object(),
            projection,
            _Registry((pre, unsupported)),
            profiles,
        )
