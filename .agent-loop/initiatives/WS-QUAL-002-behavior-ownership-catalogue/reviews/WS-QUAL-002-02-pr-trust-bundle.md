# Workstream PR Trust Bundle

## Chunk

`WS-QUAL-002-02` - Local Coverage-Context Evidence

## Goal

Emit bounded, non-authoritative callable-to-test candidate evidence from exact
local coverage contexts without adding hosted CI infrastructure.

## Intent And Planning Context

- Intent: `../INTENT.md`
- Chunk contract: `../chunks/WS-QUAL-002-02-context-evidence.md`

## What Changed

- Added manual `context-evidence` generation and validation commands.
- Reused semantic-lane collection and completion custody.
- Mapped per-test coverage contexts to exact callable spans.
- Added digest, exact-head, clean-tree, runtime, size, path, overwrite, privacy,
  and non-authoritative-schema controls.
- Added focused fail-closed tests and operational documentation.

## Why It Changed

Imports and coverage totals do not show which exact tests execute a callable.
This bounded evidence makes later ownership review better informed without
claiming that inferred execution proves assertions or reviewed ownership.

## Design Chosen

One local-only artifact uses the existing lane plugin for collection and
completion, coverage.py test contexts for line evidence, and an independent
schema that catalogue validation cannot consume.

## Alternatives Rejected

- Hosted collection was rejected because this calibration chunk must add no CI
  cost or required gate.
- Import-based inference was rejected because importing code does not prove
  behavior execution.
- Automatic catalogue population was rejected because candidate evidence is
  not reviewed ownership.

## Scope Control

### Allowed Files Changed

- WS-QUAL-002 plan, status, contract, and review evidence.
- `backend/scripts/behavior_ownership.py` and `run_test_lanes.py`.
- Their focused tests and backend testing operations documentation.

### Files Outside Stated Scope

- None.

## Product Behavior

- [x] No Workstream product behavior changed.
- [ ] Product behavior changed and is explained here.

## Evidence

### Commands Run

```bash
cd backend
.venv/bin/ruff check scripts/behavior_ownership.py scripts/run_test_lanes.py \
  tests/test_behavior_ownership.py tests/test_ci_test_lanes.py
.venv/bin/python -m pytest -q \
  tests/test_behavior_ownership.py tests/test_ci_test_lanes.py
.venv/bin/coverage erase
.venv/bin/python -m pytest -q --cov=scripts.behavior_ownership \
  --cov-report=term tests/test_behavior_ownership.py
python3 ../scripts/check_markdown_links.py
python3 ../scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

### Result Summary

```text
124 focused tests passed.
90 behavior-ownership tests passed.
scripts.behavior_ownership coverage: 91 percent.
Ruff, Markdown links, stale wording, and diff integrity passed.
```

The exact implementation-head calibration completed 90 nodes in 18.12 seconds
and emitted 141,701 bytes, below both adoption limits.

## Acceptance Criteria Proof

- [x] Exact head, callable lines, and collected nodes are bound and validated.
- [x] Collection and completion reuse `run_test_lanes.py`.
- [x] Candidate evidence cannot satisfy reviewed catalogue ownership.
- [x] The artifact is local, separate, non-catalogue, and never committed.
- [x] No workflow or required check invokes the command.
- [x] Runtime and artifact size remain below two minutes and 10 MiB.
- [x] Artifact fields exclude environment values, secrets, payloads, and logs.
- [x] Validation fails closed on stale, partial, skipped, deselected,
  digest-mismatched, overwritten, or timeout evidence.

## Test Delta

### Tests Added

- Context artifact identity, digest, exact-head, callable, path, size, runtime,
  collection, completion, skip/deselect, coverage, and privacy behavior.
- Minimal sanitized collection environment and timeout forwarding.

### Tests Modified

- Existing collection mocks accept the canonical optional timeout contract.

### Tests Removed Or Skipped

- None.

## Internal Reviewer Results

Reviewed implementation SHA: `836865b1d84d06f534c0c45f551e72f335d810aa`

Reviewed at: 2026-08-09

Reviewer run IDs: `qual002_02_{arch,qa,security,ci,reuse,test_delta}`

| Reviewer | Result | Blocking Findings | Notes |
|---|---:|---|---|
| Senior engineering | N/A - proportionate L1 review | None | Required focused tracks cover this bounded tool |
| QA/test | PASS AFTER FIXES | None | Exact-head and fail-closed custody repaired |
| Security/auth | PASS AFTER FIXES | None | Environment, path, digest, and Git custody reviewed |
| Product/ops | N/A - no product behavior | None | Local engineering evidence only |
| Architecture | PASS | None | Non-authoritative boundary preserved |
| CI integrity | PASS | None | No workflow or gate weakening |
| Docs | N/A - focused operational update | None | Links and stale wording pass |
| Reuse/dedup | PASS | None | Canonical collector reused |
| Test delta | PASS | None | Additive tests; none skipped or weakened |

## External Review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | PASS AFTER FIXES | Valid earlier findings addressed; newest run rate-limited |
| GitHub checks | Pending | Exact-head checks are running |

## CI And Gate Integrity

- [x] No workflow weakening.
- [x] No lint/test/docstring gate weakening.
- [x] No coverage threshold weakening.
- [x] No package script weakening.
- [x] No unpinned new GitHub Action.
- [x] Checkout credential persistence disabled where checkout is used.

## Remaining Risks

The artifact is candidate evidence only. It cannot establish reviewed ownership
and no authoritative catalogue consumer accepts it.

## Follow-Up Work

Use this evidence during later bounded catalogue-population chunks. Promote a
public lane-runner API only if a second consumer needs the same custody path.

## Human Review Focus

Please inspect the non-authoritative boundary, shared runtime budget,
secret-free subprocesses, exact-head callable custody, and lack of hosted-CI
changes.

## Human Merge Ownership

- [x] I can explain what changed.
- [x] I can explain why it changed.
- [x] I know what could break.
- [x] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
