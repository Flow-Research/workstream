# PR Trust Bundle: WS-XINT-003 Planning

## Chunk

`WS-XINT-003-PLAN` — REV-AUTH End-to-End Contract Planning.

## Goal

Define one fail-closed authorization chain for the complete human review and
revision lifecycle before implementing AUTH-12D2 or REV runtime behavior.

## Human-approved intent

The human requested the same end-to-end AUTH dependency review for REV that was
previously completed for ART, while preserving the existing ART-AUTH custody.

## What changed

Added intent, discovery, plan, decisions, risks, status, review evidence, chunk
map, and twelve planning/chunk contracts under `WS-XINT-003`.

## Why it changed

REV authority was distributed across AUTH, REV, and XINT-002 contracts. The
review found a concrete REV-03P/AUTH-12D2 policy ownership collision, missing
privileged action registration, globally shared action availability, and an
unsafe response-evidence order.

## Design chosen

REV owns lifecycle semantics; AUTH owns identity/evaluation/PREP/evidence; ART
and shared submission-artifact actions remain with XINT-002; CON remains a
flush-only atomic participant. Registration and activation remain separate.

## Alternatives rejected

Per-REV-chunk AUTH invention, direct grant reads in REV, generic contexts,
generic artifact access, duplicate policy writers, and activation before hidden
feature readiness.

## Scope control

Planning Markdown only. No backend code, migration, action availability, route,
worker, or product behavior changed. Chunks 02-09 are explicitly
non-implementable until refreshed with exact current-main files and commands.

## Product behavior

Unchanged. Review routes/actions remain unavailable.

## Acceptance criteria proof

- Complete human, Project Manager, Operator, and fixed-service inventory.
- One policy persistence/writer path required.
- Exact reviewer current-work, self-review denial, lease/packet/evidence,
  decision, revision, recovery, and conformance boundaries specified.
- XINT-002 ART/shared-submission custody preserved.
- Four missing privileged actions receive registration-only wave 08R.
- Both `review.reconcile.run` identities activate in one global ActionId wave.

## Tests/checks run

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `git diff --check`

No runtime tests are applicable to a planning-only Markdown change. Hosted CI
must still pass on the exact PR head.

## Test delta

No tests changed or weakened. Later chunk contracts require PostgreSQL races,
PREP denial matrices, service all-pairs denial, atomic fault injection, focused
90-percent coverage, and hosted repository coverage.

## CI integrity

No workflow, package, Ruff, pytest, coverage threshold, exclusion, or skip was
changed.

## Reviewer results

Architecture and docs: PASS. Security, product/ops, QA, and senior engineering:
PASS WITH LOW RISKS; every low/informational wording risk was also corrected.

## External review

Pending GitHub Actions and CodeRabbit on the planning PR.

## Remaining risks

Future activation chunks must refresh exact owner manifests, files, migration
head, commands, and runtime owner evidence from then-current main.

## Follow-up work

After human merge and explicit request, execute `WS-XINT-003-01`. AUTH-12D2 and
REV-03P runtime work must wait for that ownership/custody reconciliation.

## Human review focus

Review policy ownership, the XINT-002 boundary, response-evidence sequencing,
08R registration, single-wave reconciliation activation, and chunk order.

## Human merge ownership

Only the human may merge this PR.
