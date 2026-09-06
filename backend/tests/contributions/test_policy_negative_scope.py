"""Static public command surface, not proof of runtime side-effect isolation."""

from app.modules.contributions.service import ContributionPolicyService


def test_cp04b_exposes_only_hidden_policy_commands() -> None:
    public = {name for name in dir(ContributionPolicyService) if not name.startswith("_")}
    assert public == {"create_draft", "publish", "read", "retire", "update_draft"}
