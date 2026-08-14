# WS-ARCH-001-CP02 PR Trust Bundle

## Chunk

`WS-ARCH-001-CP02` planning correction: Hidden Adapter-Binding Behavior.

## Goal

Turn the stale CP02 skeleton into a current-main executable contract before any
implementation begins.

## Human-approved intent

Plan the exact hidden CON-owned adapter-binding lifecycle first. Preserve AUTH
as the sole authorization owner, keep the behavior unreachable and unavailable,
and return to implementation only after this planning PR merges and receives
explicit human approval.

## What changed

- Defined hidden create/read/suspend/resume behavior and exact state transitions.
- Defined immutable requests, results, owner-capability ports, query
  authorization, and an opaque mutation-authorization port.
- Defined migration `0004`, lifecycle-event history, concurrency/idempotency,
  database guards, fail-closed proof, tests, reviewers, and stop conditions.
- Defined transaction-retained owner eligibility fences and authorized
  unknown-commit recovery before any duplicate mutation authorization.
- Reconciled ARCH, CON, roadmap, and current-state records.
- Recorded the architectural decision and newly identified risks.

## Why it changed

The former skeleton could not safely guide implementation. It omitted the
public consume boundary, exact migration rules, service-actor eligibility,
tenant-safe loading, lifecycle history, and deterministic duplicate behavior.

## Design chosen

CON owns binding commands, results, row locks, lifecycle rules, repository,
service orchestration, and immutable lifecycle history. AUTH owns action
availability, Finance Authority evaluation, opaque PREP machinery, decisions,
and decision evidence. Read uses request-scoped authorization. Mutations use a
CON-facing opaque prepare/consume/close port that CP03 will adapt to the existing
AUTH protocol.

## Alternatives rejected

- Generic service-actor eligibility: unrelated ART/REV identities could bind.
- AUTH-private imports: violate modular-monolith extraction boundaries.
- A second CON-local authorization protocol: duplicates security machinery.
- Replaying success for duplicate operations: complicates revocation and can
  disclose prior state; duplicates instead receive one concealed conflict.
- Clearing suspension fields without immutable history: loses attribution.

## Scope control

Planning and current-state documentation only. No runtime code, migration,
route, evaluator, grant, service identity, matrix row, action activation,
provider behavior, policy behavior, retirement, fulfillment, or compatibility
path is added.

## Product behavior

Unchanged. All four adapter-binding actions remain planned/unavailable and no
route can reach the future behavior.

## Acceptance criteria proof

The contract now names exact scope, non-goals, public types and ports, owner
capabilities, read and mutation ordering, transition invariants, immutable
history, migration behavior, failure cases, verification, reviewers, human
focus, stop conditions, and merge outcome.

## Tests/checks run

Stale authorization wording, stale Workstream wording, changed Markdown links,
atomic chunk-state synchronization, and `git diff --check` all pass.

## Test delta

No tests changed because this PR changes planning only. The future contract
requires focused unit tests, PostgreSQL schema/lifecycle tests, concurrency
tests, reset tests, boundary tests, and hosted full-coverage proof.

## CI integrity

No workflow, test command, coverage floor, ledger exception, skip, or gate was
weakened. Hosted CI remains required before this PR is ready to merge.

## Reviewer results

- Architecture status: pass.
- Security/authorization status: pass.
- Product/operations status: pass. Low-risk history-link concern was fixed.
- Documentation status: pass. Two findings were fixed.
- Senior engineering status: pass. Three findings were fixed.

## External review

CodeRabbit produced seven valid bounded findings on the first published head.
All were fixed and recorded in the external-review response. GitHub's live
exact-head checks remain the authority for transient hosted CI and CodeRabbit
state; this durable bundle does not preserve a stale pending/passing claim.

## Remaining risks

Implementation remains L1. Its actual migration, concurrency behavior, opaque
handle semantics, public boundary composition, and denial side-effect ordering
must receive fresh focused review.

## Follow-up work

After human merge and explicit approval, implement CP02 only. CP03 later installs
the real AUTH/ACTORS adapters and activates exactly the proven actions. Broader
ContributionPolicy behavior remains in later chunks.

## Human review focus

- CON lifecycle ownership versus AUTH decision ownership.
- Exact `instrument_type` and `route_key` parity without translation.
- Query-only read versus opaque PREP mutations.
- Immutable suspension/resume attribution and one-effect duplicate handling.
- No activation or broader CON lifecycle work in this PR.

## Human merge ownership

Only an authorized human may approve and merge this PR.
