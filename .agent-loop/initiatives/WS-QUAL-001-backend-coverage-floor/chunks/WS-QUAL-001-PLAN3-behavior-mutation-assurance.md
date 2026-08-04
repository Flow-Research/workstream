# Chunk Contract: WS-QUAL-001-PLAN3 — Behavior And Mutation Assurance Planning

## Parent initiative

`WS-QUAL-001` — Behavior And Mutation Assurance

## Goal

Replace the unstarted global-90 floor proposal with reviewed, bounded planning
for behavior-owned changed-scope mutation assurance while retaining the global
78-percent floor.

## Why this chunk exists

Main already exceeds 90-percent statement coverage, but no executable gate
proves assertion sensitivity. Planning must define a safe pilot and a separate
calibrated enforcement step before workflow or dependency changes.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/CHUNK_MAP.md`

## Risk class

L1 — CI/test policy planning.

## SLA

P2.

## Allowed files

```text
.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**
```

## Not allowed

```text
application or test implementation
workflow, dependency, threshold, coverage, or mutation-engine changes
revival of retired signed-loop, merge-intent, or machine-scope machinery
automatic start of 04M or 05M
```

## Acceptance criteria

- [ ] Current main coverage, runtime, and existing test-integrity gates are
      recorded exactly.
- [ ] The global 78-percent and protected 90-percent floors are preserved.
- [ ] Planning distinguishes behavior evidence from statement coverage.
- [ ] Pilot selection covers changed production targets and explicit test-only
      behavior claims without full-repository mutation.
- [ ] Runtime, dependency, evidence, classification, cache, and worktree-safety
      risks have fail-closed controls.
- [ ] Blocking rollout requires accepted pilot evidence and a new human gate.
- [ ] Required internal planning reviewers pass with no open sessions.

## Verification commands

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

- Confirm 78 percent remains the global floor.
- Confirm mutation assurance measures behavior rather than another percentage.
- Confirm the pilot is bounded and the blocking rollout has a separate human
  checkpoint.

## Stop conditions

Stop if planning implies immediate blocking mutation, full-repository mutation,
coverage/Backend weakening, an unbounded dependency/runtime commitment, or any
implementation change.
