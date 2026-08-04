# WS-ART-001 PLAN5 PR Trust Bundle

## Chunk

`WS-ART-001-PLAN5` — Legacy Precheck Clean-Cut Resequencing

## Goal

Remove the complete legacy contributor precheck once and for all without ever
exposing unchecked Submission creation or preserving a compatibility seam.

## Human-Approved Intent

The user explicitly chose complete legacy removal and approved updating the
plan now instead of keeping a partial private path.

## What Changed

- superseded proposed runtime chunk 04A4;
- made 04B1 the next ART implementation chunk;
- expanded 05B to remove the standalone route, schemas, public service entry,
  internal legacy guard, and caller-owned package authority together;
- aligned canonical architecture, AUTH, glossary, operations, template, and
  current-data-flow wording;
- strengthened 05B state, replay, concurrency, dispatch, and reachability proof.

## Why It Changed

Live legacy `TaskService.create_submission` still uses the same precheck service
as the standalone route. Early service deletion would permit unchecked
Submission creation, break the live path, or require a forbidden compatibility
service. The verified-admission replacement is not live until later chunks.

## Design Chosen

Freeze the legacy path without extending it while 04B1-04C2 and 05A build the
authoritative replacement. At 05B, make verified admission consumption the only
Submission path and delete every legacy entry and caller-owned identity field in
the same cutover.

## Alternatives Rejected

- Early complete deletion: replacement is not live.
- Route-only deletion with private legacy service: creates a partial cleanup and
  a compatibility seam.
- Dual old/new paths: permits authority ambiguity and duplicate business effects.

## Scope Control

Planning and documentation only. No application code, database migration,
runtime schema, route, service, workflow, AUTH availability, or executable test
changed.

## Product Behavior

No product behavior changes in PLAN5. Current legacy behavior remains frozen
until 05B; the target behavior remains one continuous ZIP preparation and
admission-backed Submission path.

## Acceptance Criteria Proof

- 04A4 is superseded and authorizes no runtime work.
- 04B1 is explicitly next after PLAN5.
- 05B owns the entire legacy clean cut.
- No alias, fallback, private compatibility service, or second registry is
  planned.
- Current and target-state documentation are explicitly distinguished.

## Tests And Checks Run

```text
git diff --check
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
PYTHONPATH=. python3 scripts/test_lightweight_agent_gates.py
```

All passed.

## Test Delta

No executable tests changed. Future 05B obligations were strengthened to cover
admission states, cross-resource denial, mixed requests, replay, concurrency,
single dispatch, route/OpenAPI absence, and import/public-service reachability.

## CI Integrity

No workflow or gate changed. Existing 90 percent subsystem and 78 percent
repository coverage requirements remain. Exact 05B shell commands and include
paths must be locked before 05B implementation.

## Reviewer Results

Architecture, product/ops, QA, docs, reuse, and test delta: PASS. Security and
senior engineering: PASS WITH LOW RISKS after repairs. CI integrity: PASS WITH
CONDITIONS applying only before future 05B implementation.

## External Review

GitHub CI and CodeRabbit begin after this planning branch is pushed.

## Remaining Risks

The frozen legacy path still exists until 05B, but receives no new behavior and
remains mandatory for legacy Submission safety. 05B must not begin until the
verified-admission replacement and required AUTH activation are merged.

## Follow-Up Work

After human merge, implement only 04B1. Do not start 04B2 automatically.

## Human Review Focus

- Is one complete 05B deletion preferable to partial early cleanup?
- Are all legacy surfaces named in the 05B contract?
- Does the sequence preserve checked Submission creation at every point?

## Human Merge Ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] I explicitly approve this PR for merge.
