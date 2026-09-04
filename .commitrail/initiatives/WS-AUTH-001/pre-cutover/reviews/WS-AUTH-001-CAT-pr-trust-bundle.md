# PR Trust Bundle: WS-AUTH-001-CAT

## Chunk

`WS-AUTH-001-CAT` - Action And Resource Catalogue Reconciliation

## Goal And Human-Approved Intent

Review the proposed catalogue against the live repository, copy only validated
rules into canonical docs and owning future chunks, reject incompatible content,
then resume AUTH-05B after this docs-only amendment merges.

## What Changed And Why

- Added a staged typed `ActionId`/`PermissionId` model to the canonical AUTH spec.
- Updated AUTH-07 through AUTH-16 contracts with exact ownership, conformance,
  evidence, coverage, and audit-parity requirements.
- Preserved 52 approved permission identifiers while recording the current
  49-identifier persisted audit base and planned recovery transition.
- Reconciled future AUTH migration custody through `0026`.
- Recorded D15 and current loop state.
- Removed the rejected root proposal instead of committing a competing authority.

The change is needed because the input contained sound authorization mechanics
but contradicted merged API, audit, model, and cross-domain contracts.

## Design Chosen

Routes and commands declare exact stable `ActionId` values. Each active action
maps to one approved `PermissionId`, canonical target, typed resource facts, and
guard set. Multiple actions may map to one retained broad permission. Planned
metadata is non-executable and cannot predesign resources owned by WS-REV,
WS-CON, or artifact storage. Feature services remain canonical resource owners.

## Alternatives Rejected

- Treating the input as a normative addendum.
- Replacing broad permission identifiers without audit/schema migration.
- Adding `/v1` or a compatibility route tree.
- Centralizing feature queries inside AUTH.
- Inventing artifact outbox/recovery or future review/compensation aggregates.
- Deferring missing route declarations or coverage regressions until AUTH-16.
- Recording only broad permission when exact action identity affects guards.

## Scope And Product Behavior

The patch changes Markdown only. It does not activate authorization, change an
API, alter a permission, migrate data, modify product lifecycle behavior, or
start AUTH-05B. Current runtime behavior remains unchanged.

## Acceptance Proof And Checks

All chunk acceptance criteria are reflected in the canonical spec, D15, and
owning future chunk contracts. Stale wording, authorization-doc, artifact
contract, Markdown-link, and diff-integrity checks pass.

No tests were added, changed, removed, skipped, or weakened. No CI, dependency,
coverage threshold, or configuration changed.

## Reviewer Results

Senior engineering, architecture, docs, QA/test, security/auth/privacy, and
product/ops passed after all valid findings were repaired. Full details are in
`WS-AUTH-001-CAT-internal-review-evidence.md`.

## External Review

Backend and Agent Gates passed. CodeRabbit raised two valid documentation
consistency comments: preserve the 52-approved/49-persisted distinction and
remove a stale second AUTH-05B start requirement. Both are repaired and recorded
in `WS-AUTH-001-CAT-external-review-response.md`; CodeRabbit re-review and human
review remain.

## Remaining Risks And Follow-Up

The catalogue is a future implementation contract, not runtime proof. AUTH-05B
remains the next runtime chunk and is unaffected by this action catalogue.
AUTH-07 must implement the registry/evidence design; route-owning chunks must
prove activation incrementally; later domain initiatives require their own
approved resources and permission migrations.

## Human Review Focus

Confirm the 52-approved/49-persisted distinction, `ActionId` evidence, domain
ownership, planned/active boundary, per-chunk 90 percent coverage, and migration
sequence. Confirm that no rejected catalogue content entered canonical docs.

## Human Merge Ownership

Only the user may explicitly approve and merge this PR. AUTH-05B begins only
after this amendment merges and loop memory is current.
