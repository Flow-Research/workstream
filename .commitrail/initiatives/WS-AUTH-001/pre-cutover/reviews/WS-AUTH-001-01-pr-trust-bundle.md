# PR Trust Bundle: WS-AUTH-001-01

## Chunk

`WS-AUTH-001-01` - Adopt Authorization Baseline And Repository Contracts

## Goal

Make the adopted authorization model, canonical `/api/v1` namespace,
superseded bootstrap behavior, recovery permissions, and implementation order
unambiguous before application code changes.

## Human-Approved Intent

The user explicitly approved D4-D10 and started only WS-AUTH-001-01 on
2026-07-11. No later auth or policy chunk is activated.

## What Changed And Why

- Added ADR 0012, a canonical authorization spec, and an operations runbook.
- Reconciled active docs and diagrams so token roles and typed profiles are not
  product authority; local grants and guards are canonical.
- Added a fail-closed scanner, independent regression tests, Agent Gates step,
  and bounded rendering command to prevent documentation drift.
- Recorded PR #90 as independently owned while preserving its approved
  correction/activation contract in shared docs.

## Design Chosen

External Flow identity verifies authentication facts. Workstream resolves
canonical actors and evaluates system/exact-project grants, registered
permissions, resource/lifecycle guards, revocation, idempotency, invalidation,
and append-only evidence. The scanner rejects authority-shaped token/profile
wording uniformly instead of trying to interpret English negation.

## Alternatives Rejected

- Workstream-owned login/session flows: violates the external auth boundary.
- Token roles or typed workflow profiles as product authority: not durable,
  scoped, or immediately revocable.
- A second short API namespace or compatibility alias: creates contract drift.
- Natural-language negation parsing in the scanner: adversarially ambiguous.
- Splitting the active-doc reconciliation: leaves contradictory canonical docs.

## Scope Control

The authored diff contains docs, loop memory, diagram sources/generated
companions, one scanner, one renderer, scanner tests, one additive CI step, and
three exact backend files whose only authored changes replace human `worker`
prompt/assertion wording with Contributor. It contains no authored runtime
logic, schema, migration, dependency, package, or lockfile changes. Merged PR
#90 code appears only through the latest-main merge. All eight imported sources,
`SHA256SUMS`, and `SOURCE_MANIFEST.md` are unchanged.

## Product Behavior

No authored runtime behavior changes. Review decisions remain `accept`,
`needs_revision`, and `reject`. Merged PR #90 correction supersedes and retains
unapproved compiled output with bounded correction provenance, requeues
correction-aware derivation, rejects an unchanged replacement, and keeps
activation blocked until the current provenance-matched compiled policy is
approved.

## Acceptance Proof

- Canonical ADR/spec/runbook and ownership policy exist.
- Five administrative and three exact-project contributor grants are stable.
- `/api/v1` is canonical with no alias.
- Active docs, diagrams, roadmap, and durable memory are reconciled.
- Scanner auto-discovers tracked/untracked active docs and fails closed.
- Imported source hashes and direct diff checks prove byte immutability.

## Tests And Checks

- 31 agent-gate regression tests passed.
- 234 project backend tests passed in 3576.81 seconds.
- 2 focused agent-runtime prompt tests passed after the CI assertion repair.
- Stale authorization and Workstream wording scans passed.
- Markdown links passed for 68 changed Markdown files.
- Loop-memory validation and `git diff --check` passed.
- Eight archival SHA-256 checks passed.
- Python and renderer shell syntax passed.
- Pinned local render completed twice with stable artifact hashes.

## Test Delta And CI Integrity

Existing tests were not removed, skipped, or weakened. New fixtures are
independent of production rule definitions. Agent Gates invokes the scanner
directly without `continue-on-error`; no existing gate or threshold changed.

## Reviewer Results

All required tracks passed against implementation freeze
`be0b836`, including the CI assertion repair, and the latest-main lifecycle
state was reviewed at final bound SHA
`3815bbd2ade4ada7f03be611282d38e93dba1b7e`: senior engineering, QA/test,
security/auth, product/ops, architecture, docs, reuse/dedup, CI integrity, and
test delta. The circuit breaker accepted the documented atomic-docs size
exception.

## External Review

PR #93 is published. GitHub checks, CodeRabbit follow-up, and human review remain
pending.

## Remaining Risks And Follow-Up

- Rendering is locally repeatable but not fully cross-host hermetic beyond the
  pinned PlantUML JAR.
- The externally requested "authorization implementation until auth proof"
  contract phrase remains an acknowledged low wording risk.
- Production issuer inputs and runtime authorization remain owned by later
  bounded chunks.
- `WS-AUTH-001-02` and `WS-POL-002-04` remain inactive.

## Human Review Focus

Confirm authority precedence, stable grant/permission names, `/api/v1`,
recovery boundaries, PR #90 interaction, and that no runtime/review/compensation
behavior was adopted accidentally.

## Human Merge Ownership

Only the user may approve and merge this PR. Publication is not merge approval.
