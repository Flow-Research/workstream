# Chunk Contract: WS-QUAL-001-PLAN2 — Current-Main Coverage Reconciliation

Parent initiative: `WS-QUAL-001`

## Goal

Replace the obsolete milestone ladder with an evidence-backed closure plan from
the current hosted 88.954981-percent baseline.

## Risk class and SLA

L1 CI/test-policy planning; P2.

## Allowed files

- `.agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/**`

## Not allowed changes

- Application, test, workflow, CI, dependency, or coverage configuration files.
- Any AUTH, ART, REV, CON, or external-contributor PR/branch.

## Acceptance criteria

- Exact hosted counts and timing are recorded.
- Completed historical work is separated from stopped/superseded experiments.
- Remaining work is PR-sized and keeps the threshold switch separate.
- Test quality and runtime guardrails are explicit.
- Required plan reviewers pass.

## Verification commands

- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_markdown_links.py`
- `git diff --check`

## Required reviewers

Plan, senior engineering, QA/test, CI integrity, architecture, product/ops, and
docs. Security is not applicable because no runtime/auth behavior changes.

## Human review focus and stop

Confirm the simplified sequence and baseline. Stop after the planning PR; no
test or threshold implementation starts from this contract.
