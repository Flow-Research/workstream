# WS-CI-001-01R1 PR Trust Bundle

## Goal

Repair the merged backend CI workflow so isolated child-runner timeouts remain
below GitHub job budgets and cleanup can run before hard cancellation.

## Trigger

CodeRabbit posted one valid major stability finding on PR #163 after its final
review cycle. PR #163 was merged before the repair commits were pushed, so this
bounded follow-up is based on trusted merged `main` and has its own merge intent.

## What changed

- Shard child timeout: 12,600 seconds to 4,800 seconds inside a 90-minute job.
- API E2E child timeout: 3,600 seconds to 1,500 seconds inside a 30-minute job.
- Agent-gate assertions bind both values and minimum configured budget gaps.
- External review evidence records the finding, response, proof, and residual
  infrastructure risk.

These gaps provide operational cleanup headroom but are not guaranteed cleanup
durations because checkout, installation, and migration also consume job time.

## Scope control

No application code, schema, dependency, test selection, coverage threshold,
required check, permission, authentication, authorization, product lifecycle,
or merge authority changed. `WS-CI-001-02` remains inactive.

## Evidence

- Ruff formatting and lint passed.
- Shard and coverage-contract tests: 204 passed.
- Real PostgreSQL isolation and cleanup tests: 16 passed.
- Agent-gate workflow tests: 91 passed.
- Markdown links, stale wording, loop state, and diff integrity passed.

## Internal review

All nine tracks passed the rebased repair. Senior engineering, architecture,
docs, and reuse/dedup then confirmed the valid chunk-map repair.

## Remaining gates

Hosted Backend, Agent Gates, CodeRabbit, human review, and explicit merge
approval remain mandatory.

## Human review focus

Confirm timeout values remain sufficient for observed workloads, strictly below
job budgets, and preserve child termination, database cleanup, and fail-closed
propagation.
