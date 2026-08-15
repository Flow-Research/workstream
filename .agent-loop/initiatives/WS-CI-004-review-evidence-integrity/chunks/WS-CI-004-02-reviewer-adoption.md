# Chunk Contract: WS-CI-004-02 — Reviewer Adoption

## Merge state

- Outcome on merge: `complete`

## Goal

Adopt the shared Reviewer Evidence Protocol across all nine repository reviewer
skills and their matching custom reviewer agents, then prove the contracts with
one deterministic evaluation harness and isolated forward evaluations.

## Why this chunk exists

The protocol and target sensor now exist, but reviewers still use independent
thin prompts that do not require exact-head freshness, prior-finding replay,
evidence provenance, uncertainty, or cross-specialty handoff.

## Risk class

L1 / P1 — engineering review trust infrastructure.

## Allowed files

```text
.agents/skills/architecture-review/SKILL.md
.agents/skills/ci-integrity-review/SKILL.md
.agents/skills/docs-review/SKILL.md
.agents/skills/product-ops-review/SKILL.md
.agents/skills/qa-review/SKILL.md
.agents/skills/reuse-dedup-review/SKILL.md
.agents/skills/security-review/SKILL.md
.agents/skills/senior-engineer-review/SKILL.md
.agents/skills/test-delta-review/SKILL.md
.codex/agents/architecture-reviewer.toml
.codex/agents/ci-integrity-reviewer.toml
.codex/agents/docs-reviewer.toml
.codex/agents/product-ops-reviewer.toml
.codex/agents/qa-reviewer.toml
.codex/agents/reuse-dedup-reviewer.toml
.codex/agents/security-reviewer.toml
.codex/agents/senior-engineer-reviewer.toml
.codex/agents/test-delta-reviewer.toml
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/REVIEWER_MATRIX.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/evaluations/CASES.json
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/evaluations/EXPECTATIONS.json
scripts/reviewer_contracts.py
scripts/test_reviewer_contracts.py
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/CHUNK_MAP.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/STATUS.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/chunks/WS-CI-004-02-reviewer-adoption.md
.agent-loop/CURRENT_STATE.md
```

## Not allowed

```text
.github/workflows/**
review-target or receipt-schema changes
receipt custody, writer, or convergence orchestration
hosted validation or blocking evidence gates
implementation authorization, merge authority, or GitHub permissions
product/runtime/API/schema/migration code
dependencies or model changes
unrelated skills or agent prompts
the separate open implementation PR
```

## Acceptance criteria

- All nine specialty skills explicitly compose with, rather than duplicate,
  `reviewer-evidence-protocol` and retain distinct ownership questions.
- All nine custom reviewer agents require their matching specialty skill and the
  shared protocol, remain read-only, and reject final verdicts without matching
  clean start/end targets.
- Every reviewer output includes the exact target, reviewer/run identity,
  executed versus inspected evidence, stable findings and replay dispositions,
  uncertainty, freshness, and a closed verdict. Specialty-owned sections remain
  outside the closed JSON receipt and must not add fields to its schema.
- Critical/High findings block; Medium findings require an explicit human
  disposition; Low/Informational findings remain visible. Reviewers never
  silently drop prior findings or approve solely because tests pass.
- The initiative-scoped `REVIEWER_MATRIX.md` gives each reviewer a
  non-overlapping primary ownership
  contract, required unchanged context, handoff boundaries, and positive,
  negative, stale/replay, output-contract, and cross-specialty evaluation cases.
- A deterministic Python harness validates the complete 9x agent/skill matrix,
  protocol composition, closed tokens, required evaluation case classes, and
  sample receipt/output structure without executing models or trusting prose
  summaries as proof.
- Focused tests fail when one reviewer, protocol reference, required output
  field, evaluation class, or handoff rule is missing; no network is required.
- `evaluations/CASES.json` contains only raw case evidence and neutral task
  context. `evaluations/EXPECTATIONS.json` contains case ownership, must-find,
  must-not-invent, replay, handoff, and output requirements and is not created
  until the isolated reviewer runs have returned, preventing answer leakage in
  the first adoption evaluation.
- Isolated forward evaluations run each reviewer with only its raw case payload
  and repository instructions. Reviewer JSON is held in the orchestration
  session or a private temporary directory, validated with
  `scripts/reviewer_contracts.py validate-output`, then published after push as
  one GitHub PR evidence comment keyed by case, reviewer, evaluated head,
  classification, receipt verdict, and finding IDs. A case classification is
  evaluation data, never a final reviewer verdict. The canonical receipt is the
  only verdict and remains provisional when its inspections are dirty or stale.
  The comment is linked from the PR body and never committed as an
  exact-head receipt. Adoption fails if any reviewer
  misses its owned defect, invents a finding in the negative case, loses a prior
  finding after a head change, omits a required handoff, or omits the protocol
  envelope. A failed case is repaired and rerun before final exact-head review.
- Engineering verdicts remain separate from Workstream product decisions
  `accept`, `needs_revision`, and `reject`.
- No reviewer gains write, execution, contribution, approval, or merge
  authority from the protocol or its evidence.

## Verification commands

```bash
python3 -m unittest -v scripts.test_reviewer_contracts
python3 -m unittest -v scripts.test_review_target scripts.test_git_delta scripts.test_lightweight_agent_gates
python3 scripts/reviewer_contracts.py
python3 scripts/reviewer_contracts.py validate-fixtures
# Manual gate before ready-for-review: run every isolated case before
# EXPECTATIONS.json is created; create expectations only after outputs return;
# validate each JSON against its canonical receipt (or the complete set with
# `validate-output-set --output <cases> --receipts <receipts>`); after
# push publish the case/reviewer/head/classification/receipt-verdict/finding-ID
# summary as one PR comment and link it from the PR body.
python3 scripts/review_target.py --base origin/main --head HEAD --format json
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

## Required reviewers

Architecture, security, QA/test, CI integrity, senior engineering,
documentation, product/operations, reuse/dedup, and test delta.

## Human review focus

Confirm every reviewer is materially stronger and still specialty-bounded;
shared evidence rules must not turn nine reviewers into one duplicated generic
prompt or create a new approval authority.

## Stop conditions

Stop if adoption requires hosted services, model/runtime changes, mutable
receipt custody, workflow enforcement, product code, or broad unrelated skill
rewrites.
