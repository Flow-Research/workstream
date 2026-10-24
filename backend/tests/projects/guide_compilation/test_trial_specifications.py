"""Generated execution specifications describe the available bounded trial tool."""

import pytest

from app.interfaces.project_agents import CheckSpecification, require_complete_generated_specifications
from tests.checkers.external.test_trial_policy import trial_specification
from tests.projects.guide_compilation.helpers import context, ids
from tests.projects.guide_compilation.test_check_specifications import _requirement, _with_requirement


def _admit(specification, disposition="supported_post_submit"):
    requirement = _requirement(
        disposition=disposition, check_specification=specification.model_dump(mode="json"),
    )
    require_complete_generated_specifications(context(ids()), _with_requirement(requirement))


def test_nested_trial_specification_is_available_only_in_post():
    specification = trial_specification()
    _admit(specification)
    pre = CheckSpecification.model_validate(specification.model_dump(mode="json") | {
        "execution_mode": "bounded_pre_submit",
    })
    with pytest.raises(ValueError, match="post-submit background"):
        _admit(pre, "pre_submit_capability_gap")


def test_retained_trial_gap_stays_readable_but_new_specification_uses_trial_proxy():
    body = trial_specification().model_dump(mode="json")
    body["runtime_dependencies"][-1]["provisioning"] = "runtime_gap"
    retained = CheckSpecification.model_validate(body)
    assert retained.model_dump(mode="json") == body
    with pytest.raises(ValueError, match="trial proxy provisioning"):
        _admit(retained, "post_submit_capability_gap")


@pytest.mark.parametrize("nested", [True, False])
def test_prepared_offline_material_is_scoped_to_an_actual_trial(nested):
    body = trial_specification().model_dump(mode="json")
    if not nested:
        body["runtime_dependencies"].pop()
    body["inputs"].append({
        "input_id": "offline_base", "kind": "prepared_material",
        "purpose": "The profile-pinned offline base image used by the builder.",
    })
    body["runtime_dependencies"].append({
        "dependency_id": "offline_base", "kind": "prepared_material",
        "provisioning": "trial_proxy", "purpose": "Supply only the approved offline base.",
        "unavailable_code": "material_unavailable",
    })
    body["infrastructure_failures"].append({
        "code": "material_unavailable", "condition": "The approved offline cache is absent.",
    })
    specification = CheckSpecification.model_validate(body)
    if nested:
        _admit(specification)
    else:
        with pytest.raises(ValueError, match="isolated trial dependency"):
            _admit(specification)
