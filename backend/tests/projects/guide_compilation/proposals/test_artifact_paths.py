"""Model machine fields preserve existing artifact path semantics through projection."""

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
from app.modules.checkers.api.artifact_paths import (
    is_canonical_relative_path,
    is_canonical_relative_pattern,
)
from app.modules.projects.guide_compilation.projection_payloads import policy_body
from app.modules.projects.service import PolicySetupBlocked


def proposal(**patch):
    return SubmissionArtifactPolicyProposal(
        **(
            {
                "maximum_file_size_bytes": 1000,
                "maximum_package_size_bytes": 10000,
                "required_artifacts": ("outputs/answer.md",),
                "forbidden_artifacts": ("secret*", "*.tmp"),
            }
            | patch
        )
    )


def test_nested_relative_path_and_secret_prohibition_survive_real_projection():
    value = proposal()
    body = policy_body(None, value)
    assert body["required_artifacts"][0]["path"] == "outputs/answer.md"
    assert {rule["pattern"] for rule in body["forbidden_artifacts"]} == {"secret*", "*.tmp"}


@pytest.mark.parametrize(
    "path",
    [
        "../answer.md",
        "/tmp/answer.md",
        "C:/answer.md",
        "s3://bucket/answer.md",
        "https://host/answer.md",
        "outputs\\answer.md",
        "outputs//answer.md",
        "./answer.md",
        "outputs/../answer.md",
        "outputs/./answer.md",
        "out%2fanswer.md",
        "out%252fanswer.md",
        "answer.md?signature=x",
        "answer.md#x",
        "bad\x00name",
        " Cafe\u0301.txt ",
        "$(command)",
        "bad;command",
        "outputs/*.md",
        "answer.md/",
    ],
)
def test_required_path_rejects_ambiguous_or_unsafe_representation(path):
    assert not is_canonical_relative_path(path)
    with pytest.raises(ValidationError, match="canonical relative paths"):
        proposal(required_artifacts=(path,))


@pytest.mark.parametrize("path", ["outputs/secret.txt", ".env", "config/private_key.pem"])
def test_structurally_valid_secret_requirements_remain_blocked_by_policy_owner(path):
    assert is_canonical_relative_path(path)
    value = proposal(required_artifacts=(path,))
    with pytest.raises(PolicySetupBlocked, match="conflicts with forbidden"):
        policy_body(None, value)


@pytest.mark.parametrize("pattern", ["../*.tmp", "/tmp/*", "s3://bucket/*", "out\\*", "%2e%2e/*"])
def test_forbidden_pattern_rejects_noncanonical_names(pattern):
    assert not is_canonical_relative_pattern(pattern)
    with pytest.raises(ValidationError, match="canonical relative patterns"):
        proposal(forbidden_artifacts=(pattern,))


@pytest.mark.parametrize("field", ["required_artifacts", "forbidden_artifacts"])
def test_duplicate_machine_fields_reject(field):
    with pytest.raises(ValidationError, match="unique"):
        proposal(**{field: ("outputs/answer.md", "outputs/answer.md")})


def test_required_path_conflicting_with_prohibition_rejects_at_owner():
    with pytest.raises(PolicySetupBlocked, match="conflicts with forbidden"):
        policy_body(None, proposal(forbidden_artifacts=("outputs/*",)))


def test_empty_artifact_path_rejects_at_schema_boundary():
    with pytest.raises(ValidationError) as error:
        proposal(required_artifacts=("",))
    assert error.value.errors()[0]["loc"] == ("required_artifacts", 0)
    assert error.value.errors()[0]["type"] == "string_too_short"
