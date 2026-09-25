"""Static public command surface, not proof of runtime side-effect isolation."""

from app.modules.contributions.service import ContributionPolicyService


def test_policy_owner_exposes_only_policy_operations() -> None:
    public = {name for name in dir(ContributionPolicyService) if not name.startswith("_")}
    assert public == {"create_draft", "publish", "read", "read_current", "retire", "update_draft"}
