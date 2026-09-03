# PR Trust Bundle: WS-REV-001-PLAN2

## Chunk

`WS-REV-001-PLAN2` - REV-02A Runtime Readiness Plan Refresh.

## Goal

Make the complete review/revision initiative implementation-ready against
trusted main without starting REV runtime or coding against the still-retired
task contributor fields.

## Human-approved intent

Preserve one Project Guide task pipeline, immutable Review/finding/resolution
history, exact leased Submission review, accept-only FinalAcceptance, separate
checker remediation, Review-rooted human revision rebase, and no v0.1
adjudication implementation.

## What changed

- Reconciled the full initiative, active lifecycle/data/replay documents, risks,
  decisions, conformance, test design, and executable/proposed chunk boundaries.
- Converted oversized future parents into non-executable split records.
- Added exact checker-remediation causal lineage and final human/checker source
  XOR ownership to future 02C/09A4 contracts.
- Reconciled merged AUTH-09D-A PR #148, migration `0026`, and the live AUTH
  catalogue while preserving the separate contributor foundation gate.
- Added exactly one merge intent for PLAN2 with explicit successor start.

## Why it changed

Merged AUTH, ART, CON, and cross-initiative contracts invalidated older planning
assumptions. The prior plan also combined runtime boundaries, mixed human and
checker revision rules, and lacked database-enforceable checker-remediation
causal lineage.

## Design chosen

REV owns immutable review/revision lifecycle facts and orchestration. Task owns
guide context and Submission lineage. Checker remediation reuses CheckerRun and
stores `remediation_source_checker_run_id`; human revision uses
RevisionContextPreparation. CON participates flush-only in the REV-owned commit,
ART stays behind typed capability ports, and AUTH owns authorization plus the
separate contributor clean cut.

## Alternatives rejected

- No synthetic Review or shared origin-neutral revision-obligation entity for
  checker remediation.
- No separate reviewer guide or reviewer-side rebase.
- No direct Review-decision inference for submitter contribution; it consumes
  FinalAcceptance.
- No AUTH ownership of REV source columns/constraints.
- No adjudication states, queues, actions, policy, or runtime in v0.1.

## Scope control

Only the REV initiative, four allowed active product documents including
`docs/spec_review_lifecycle.md`, and one PLAN2 merge intent changed. No backend,
migration, test, workflow, dependency, frozen `docs/reference_specs/` source
specification, AUTH/ART/CON owner plan, or handoff file changed.

## Product behavior

This PR activates no product behavior. Planned v0.1 decisions remain `accept`,
`needs_revision`, and `reject`; every committed decision/finding/resolution is
immutable, accept alone creates FinalAcceptance, and checker remediation remains
distinct from Review-rooted human revision.

## Acceptance criteria proof

The plan names exact dependencies, lock orders, transaction ownership,
database constraints, migration/backfill refusal, race tests, contribution and
artifact boundaries, child ownership, required reviewers, and explicit stops.
AUTH-09D-A is treated as merged; the contributor foundation remains fail-closed.

## Tests/checks run

Diff integrity, four stale-contract scanners, Markdown links, 87 agent-gate
tests, one-head Alembic verification, merge-intent validation, catalogue
arithmetic, and changed-scope scans all pass.

## Test delta

No executable test or runtime file changed. No assertion, skip, coverage floor,
or CI gate was weakened.

## CI integrity

Current global 78 percent coverage remains unchanged. Future materially changed
task/checker/project areas require persistent focused 90 percent gates in their
own implementation chunks. PLAN2's schema-v2 merge intent validates uniquely.

## Reviewer results

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, and CI integrity all pass on repaired reviewed SHA
`a5d6b2ced4aef4e5df316af65246e10dcdc524d1`.

## External review

CodeRabbit reported six planning/scope findings on PR #150. All six are
addressed in the external-review repair: packet-manifest ownership, chunk 08
verification commands, task-participant ownership, legacy-checker exclusion,
active-spec scope classification, and 12A child ownership. Final GitHub CI and
CodeRabbit re-review are pending; human review remains required.

## Remaining risks

The contributor-field foundation has not merged, ART/CON runtime participants
remain future owner work, two duration defaults and human revision exhaustion
semantics require explicit approval, and later migration heads must be refreshed
from current main.

## Follow-up work

After PLAN2 merges, automated memory names 02A but does not start it. AUTH must
merge the contributor foundation, then a human must explicitly start a refreshed
02A contract. Every later child follows its own gate.

## Human review focus

Review the AUTH/REV ownership boundary, checker versus human revision lineage,
02A/02A2 sequencing, transaction/lock ownership, dormant adjudication boundary,
and absence of runtime changes.

## Human merge ownership

Only the user may approve and merge this PR. Merge does not authorize 02A
implementation.
