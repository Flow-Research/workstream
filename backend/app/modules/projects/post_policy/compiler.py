"""Project the POST policy already locked by the authorized guide approval."""

from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
)


def compile_saved_post_policy(
    *, policies: LockedExternalCheckerPolicies,
) -> LockedExternalPostSubmitPolicy:
    """Validate the complete approved bundle and return its exact POST value."""
    return LockedExternalCheckerPolicies.model_validate(policies).post_submit
