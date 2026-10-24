"""Project one approved immutable external POST policy without a catalogue."""

from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    RequirementDisposition,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
)


def compile_saved_post_policy(
    *,
    result: ProjectGuideCompilationResult,
    policies: LockedExternalCheckerPolicies,
) -> LockedExternalPostSubmitPolicy:
    """Require the saved result and approved exact bindings to describe one policy."""
    result = ProjectGuideCompilationResult.model_validate(result)
    policies = LockedExternalCheckerPolicies.model_validate(policies)
    if result.status == "guide_blocked" or result.submission_artifact_policy is None:
        raise ValueError("blocked guide cannot project post-submit policy")
    requirements = {
        item.requirement_id: item
        for item in result.requirements
        if item.disposition is RequirementDisposition.SUPPORTED_POST_SUBMIT
    }
    bindings = {item.requirement_id: item for item in result.post_submit_bindings}
    entries = {item.requirement_id: item for item in policies.post_submit.entries}
    if requirements.keys() != bindings.keys() or bindings.keys() != entries.keys():
        raise ValueError("approved post-submit policy omits a required binding")
    for requirement_id, binding in bindings.items():
        entry = entries[requirement_id]
        if (
            entry.registry.capability_id != binding.capability_id
            or entry.registry.capability_version != binding.capability_version
            or entry.stage != binding.stage.value
            or entry.configuration != {
                item.name: item.model_dump(mode="json")["value"]
                for item in binding.parameters
            }
        ):
            raise ValueError("approved post-submit policy changes a required binding")
    return policies.post_submit
