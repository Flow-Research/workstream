# Plan: WS-QUAL-002 Behavior Ownership Catalogue

## Approach

1. Define a versioned catalogue schema and read-only inventory/generation CLI.
2. Produce coverage-context candidates and validate them against collected
   pytest nodes and current AST callables.
3. Pilot reviewed ownership for AUTH/actors first because it is active and
   security-sensitive.
4. Populate remaining catalogue groups in independent data PRs.
5. Require catalogue completeness and staleness checks while leaving the
   current claim gate unchanged.
6. Cut mutation selection over to protected-base catalogue ownership, requiring
   a changed catalogue record only for new/remapped behavior.
7. Prove normal AUTH work can generate selection without pausing, then retire
   routine hand-authored PR claims.

## Catalogue model

One record per eligible target. Records distinguish mutation-owned callables
from typed structural-only modules. Each owned callable binds exact collected
pytest nodes, observable outcomes, and real boundaries. A callable group is
only a storage and review convenience: it must enumerate every exact AST
callable member, and Git-delta selection still resolves and validates each
changed callable independently. Wildcards, module-wide ownership, and implicit
group membership are forbidden. Candidate evidence and reviewed test ownership
are separate states; candidate inference can never satisfy the blocking gate.

The catalogue is engineering QA and mutation evidence only. It does not create
or modify Workstream product authority, review decisions, ContributionRecords,
payment, reputation, or lifecycle truth.

## Protected authority

For existing behavior, ordinary PRs use the catalogue read from protected base.
New or remapped callables require an additive changed record validated from PR
head. PR-head data cannot delete, narrow, downgrade, or replace protected-base
reviewed ownership. Exact Git delta remains the source of changed callables.

## Verification strategy

- JSON Schema and path/custody validation.
- Exact eligible-module completeness and no-orphan checks.
- A deterministic target-to-population-group manifest that assigns every
  eligible target to exactly one of `auth`, `artifacts`, `lifecycle`, or
  `shared` before concurrent population begins.
- Exact collected-node existence and no skip/deselect weakening.
- Context-coverage candidate reconciliation.
- Negative tests for missing, narrowed, stale, renamed, deleted, duplicated,
  unsafe, and overly broad ownership.
- Focused 90-percent coverage for new catalogue tooling.
- AUTH pilot and final hosted mutation evidence within the existing job cap.

## Rejected architecture

No monolithic claim, import-only mapping, mutable runtime registry, generic
plugin discovery, global mutation score, or full-repository ordinary-PR run.

## Rollout boundary

The current 05M gate remains authoritative until the final cutover chunk is
human-approved and hosted evidence proves the catalogue path. Population work
may proceed concurrently only after both the schema/generator foundation with
its target partition (`01`) and observational context evidence (`02`) merge.
The observational context prototype cannot modify the
blocking mutation workflow; chunk `05` is the first chunk allowed to change
mutation enforcement.
