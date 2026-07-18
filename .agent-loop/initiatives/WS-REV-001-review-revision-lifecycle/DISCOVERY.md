# Discovery: WS-REV-001 Review And Revision Lifecycle

## Baseline

Discovery was refreshed read-only from trusted main
`99ae4c963e53f317175dcb308b9e47c93ccf19ed` after REV parent chunk 02 merged
through PR #147 and AUTH-09D-A merged through PR #148. The active planning chunk
makes no backend/runtime changes.

## Current backend

- FastAPI/Python, async SQLAlchemy 2.x, Alembic, Pydantic, PostgreSQL.
- Single Alembic head: `0026_actor_profile_lifecycle`.
- `Submission` is the existing versioned submission entity; no separate
  SubmissionVersion is needed.
- Both retired task-subsystem contributor-identity storage fields remain on
  trusted main. REV must not build new schema against them.
- Existing checker routing can move a Task to `needs_revision` with
  `review_decision_id=None`. The regression
  `test_checker_caused_revision_resubmits_fixed_version_through_api` proves this
  supported path.
- Existing project guide activation is a public bodyless route with legacy
  registered-actor/local-role checks, locks the candidate before Project, uses
  application time, and allows only draft activation/idempotent active repeat.
  Superseded-guide reactivation must not be added under that authorization.
- Task screening currently does not share the Project-first publication lock.

## AUTH discovery

- Trusted catalogue: 74 PermissionIds, 65 ActionIds, 15 active, 50 planned.
- AUTH-09A/09B/09C and 09D-A are merged. PR #148 merged 09D-A as
  `99ae4c963e53f317175dcb308b9e47c93ccf19ed` from reviewed head
  `9c5ef8a1feffd6324acfd947e67042921955320b`, establishing database-backed
  ActorProfile lifecycle status/provenance and migration
  `0026_actor_profile_lifecycle`.
- 09D-A intentionally leaves both retired task-subsystem contributor-identity
  fields unchanged. The user-directed contributor/canonical-human foundation
  remains separate and has no trusted-main chunk ID, PR/SHA, or migration.
- AUTH-09D-B, 09E, AUTH-PREP, REV custody, AUTH-10 through 14, and matching
  feature activations remain unmerged. AUTH-13/14 contracts require later
  amendment for prepared revision/replacement facts and cannot be treated as
  current runtime gates.
- All 24 REV lifecycle actions remain unavailable. REV never registers,
  provisions, evaluates, or activates them.

## ART discovery

- ART v2 LocalStorage clean cut merged through PR #141 at `a10d901` despite
  stale ART owner status wording.
- S3/MinIO and ART 02B1 onward remain proposed.
- Current ART map does not schedule an exact lease-scoped review packet-read
  capability, review-evidence candidate/finalize capability, or server-derived
  stabilized Submission artifact digest. REV-03B, 07A/07B, 09A3/09A4, 10, and
  projection work remain blocked on exact owner chunks.
- REV must consume typed capability ports and never ArtifactStore, concrete
  adapters, provider references, scratch paths, or ART repositories.

## CON discovery

- CON-01 canonical specification/ADR is merged; runtime 02A onward remains
  proposed on trusted main.
- An unmerged CON outbox branch also claims migration `0026`. It must rebase and
  renumber after the winning migration; REV consumes neither worktree.
- Exact planned dependencies are CON-02A outbox, 02C audit participant, 03B
  ContributionPolicyVersion, 03C contribution/award persistence, 06 lease
  freeze, 07 atomic two-operation participant, and later delivery/readiness
  hooks. Proposed contracts are not runtime proof.
- The stable boundary is reviewer contribution from Review for every decision
  and submitter contribution from accept-only FinalAcceptance.

## Product findings

- All reviewer decisions/findings/resolutions are append-only.
- Checker-caused remediation is supported but accepted ADRs scope controlled
  guide rebase/preparation to human Review revision. The plan must preserve a
  distinct CheckerRun-rooted N+1 path rather than treating it as legacy or
  silently applying human RevisionPolicy/D6 behavior. Current Submission storage
  lacks immutable causal CheckerRun lineage, so 02C must add and backfill
  `remediation_source_checker_run_id` before human prepared cutover adds the
  source XOR.
- Human revision context is task-owned. REV supplies exact human decision/
  finding facts through a typed task participant. Checker remediation retains
  its existing task/checker path and locked context.
- Task guide identity and reviewer packet access require database-enforced
  immutability/lease scope, not service convention.
- The exact decision lock order must put AUTH authority first, then
  ReviewDecisionRequest, ReviewLease, queue, task, exact Submission assignment,
  Submission, and stable subordinate rows.

## Plan-review findings incorporated

- Split unsafe oversized parents 03-07, 09A, 11, 12/12A, and 13.
- Keep 08 pure; keep 10 as the first canonical decision transaction.
- Separate 02A chronology from later hidden 02A2 reactivation. 02A2 must merge
  before AUTH-12 evaluator/cutover/activation, not after an active action.
- Move historical admission scan to authorized reconciliation child 11C.
- Separate persisted phase execution denial from static router/AUTH membership
  and operational scheduler state.
- Keep active release docs and route registration together in 13C.

## Unknowns and owner actions

- AUTH must name/merge the contributor foundation and later amend AUTH-12/13/14
  contracts.
- ART must schedule/merge packet-read, review-evidence, digest, and projection
  capabilities.
- CON must merge its runtime foundations from the then-current migration head.
- Human must approve the two positive 02B duration defaults.

Until those facts are on trusted main, REV planning may continue but runtime
must stop at each affected gate.
