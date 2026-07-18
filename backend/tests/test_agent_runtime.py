from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.adapters.project_agents.openai_agent_sdk import (
    POST_SUBMIT_POLICY_DERIVATION_INSTRUCTIONS,
)
from app.interfaces.project_agents import (
    PostSubmitCheckerPolicyDerivationResult,
)


def test_post_submit_agent_prompt_forbids_runtime_judgment_and_code() -> None:
    """Post-submit derivation remains setup-time policy work, not runtime judgment."""
    instructions = " ".join(POST_SUBMIT_POLICY_DERIVATION_INSTRUCTIONS.split())

    assert "Do not produce executable code" in instructions
    assert "Runtime submission evaluation must use the locked compiled policy" in instructions
    assert "must never ask an agent to judge a contributor submission" in instructions
    assert "Select only checker names present in registered_checker_catalog" in instructions


def test_post_submit_derivation_result_rejects_uncontracted_fields() -> None:
    """Agent output must stay inside Workstream's constrained spec shape."""
    with pytest.raises(ValidationError):
        PostSubmitCheckerPolicyDerivationResult.model_validate(
            {
                "required_checkers": [],
                "warning_checkers": [],
                "agent_version": "test-agent-v0",
                "generated_checker_code": "def run(): pass",
            }
        )
