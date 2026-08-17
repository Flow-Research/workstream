"""CP04A exposes no later lifecycle or downstream behavior."""

from app.modules.contributions.service import ContributionPolicyService


def test_cp04a_exposes_no_publish_behavior() -> None:
    assert not hasattr(ContributionPolicyService, "publish")


def test_cp04a_exposes_no_retire_behavior() -> None:
    assert not hasattr(ContributionPolicyService, "retire")


def test_cp04a_exposes_only_hidden_policy_commands() -> None:
    public = {name for name in dir(ContributionPolicyService) if not name.startswith("_")}
    assert public == {"create_draft", "read", "update_draft"}


def test_cp04a_cannot_change_current_version_identity() -> None:
    assert not hasattr(ContributionPolicyService, "set_current_version")


def _assert_no_downstream_command(name: str) -> None:
    assert not hasattr(ContributionPolicyService, name)


def test_cp04a_creates_no_project_guide_effect() -> None:
    _assert_no_downstream_command("update_project_guide")


def test_cp04a_creates_no_task_effect() -> None:
    _assert_no_downstream_command("create_task")


def test_cp04a_creates_no_submission_effect() -> None:
    _assert_no_downstream_command("create_submission")


def test_cp04a_creates_no_review_effect() -> None:
    _assert_no_downstream_command("create_review")


def test_cp04a_creates_no_contribution_record_effect() -> None:
    _assert_no_downstream_command("create_contribution_record")


def test_cp04a_creates_no_compensation_award_effect() -> None:
    _assert_no_downstream_command("create_compensation_award")


def test_cp04a_creates_no_fulfillment_effect() -> None:
    _assert_no_downstream_command("fulfill")


def test_cp04a_creates_no_callback_effect() -> None:
    _assert_no_downstream_command("callback")


def test_cp04a_creates_no_delivery_effect() -> None:
    _assert_no_downstream_command("deliver")


def test_cp04a_creates_no_reputation_effect() -> None:
    _assert_no_downstream_command("project_reputation")
