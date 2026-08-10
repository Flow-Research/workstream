# Chunk Contract: WS-CI-002-01 — Single-Head Agent Gate

## Goal

Produce one deterministic required `agent-gates` result per PR head and use
branch protection, not a CI review-API poll, for independent approval.

## Why this chunk exists

The workflow currently runs on PR changes and review changes under the same
required context. Dependency-manifest PRs fail before approval and later pass
after approval, leaving contradictory same-head results that GitHub sometimes
retains as merge blockers.

## Risk class

L1 CI and contribution authority.

## Allowed files

```text
.github/workflows/agent-gates.yml
backend/scripts/check_guide_extractor_dependencies.py
backend/tests/test_guide_extractor_dependencies.py
scripts/test_lightweight_agent_gates.py
docs/operations_backend_testing.md
.agent-loop/CURRENT_STATE.md
.agent-loop/initiatives/WS-CI-002-deterministic-agent-gates/**
```

## Not allowed

- Removing static dependency-manifest validation.
- Weakening dependency hashes, platform constraints, import boundaries, tests,
  lint, coverage, or any Backend lane.
- Reducing protected-branch approval requirements.
- Adding an approval bypass, fallback success, or `continue-on-error`.
- Changing product behavior or dependencies.

## Acceptance criteria

1. `agent-gates` runs on head-changing PR events, not review or body-edit events.
2. Superseded in-progress runs for the same PR are cancelled.
3. The dependency gate validates repository content without querying live PR reviews.
4. Obsolete review-fetching code and its tests are removed rather than retained.
5. Lightweight regression tests lock the deterministic trigger and static command.
6. Existing branch protection remains responsible for the required independent approval.
7. All affected tests and exact-head GitHub checks pass.

## Verification commands

```bash
python3 -m unittest -v scripts.test_lightweight_agent_gates
cd backend
.venv/bin/ruff check scripts/check_guide_extractor_dependencies.py tests/test_guide_extractor_dependencies.py
.venv/bin/pytest -q tests/test_guide_extractor_dependencies.py
cd ..
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

CI integrity and test delta.

## Human review focus

Confirm that review authority still comes from protected-branch approval and
that `agent-gates` now represents only deterministic repository validation.

## Stop conditions

Stop if the change weakens branch protection, dependency validation, tests,
coverage, or requires a successful check without validating repository content.
