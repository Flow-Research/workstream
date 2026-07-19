# Discovery: WS-REV-001 Review And Revision Lifecycle

## Baseline

Discovery was refreshed read-only from trusted main
`44f2467cedc266d2efe261119cfff436ac6b7715` after ART admission foundation PR
#154 merged on top of REV PLAN2 PR #150, AUTH-09D-B PR #152, and the AUTH
contributor foundation PR #153. The active parent-split repair makes no
backend/runtime changes.

## Current backend

- FastAPI/Python, async SQLAlchemy 2.x, Alembic, Pydantic, PostgreSQL.
- Single Alembic head: `0028_artifact_admission`.
- `Submission` is the existing versioned submission entity; no separate
  SubmissionVersion is needed.
- TaskAssignment and Submission now expose only `contributor_id`; each has an
  ActorProfile FK and database-enforced human-kind lineage.
- Existing checker routing can move a Task to `needs_revision` with
  `review_decision_id=None`. The regression
  `test_checker_caused_revision_resubmits_fixed_version_through_api` proves this
  supported path.
- Existing project guide activation is a public bodyless route with legacy
  registered-actor/local-role checks, locks the candidate before Project, uses
  application time, and allows only draft activation. It rejects both an
  already-active repeat and a superseded candidate. 02A3 owns the explicit
  additive no-write active repeat; superseded-guide reactivation must not be
  added under legacy authorization.
- Task screening currently does not share the Project-first publication lock.

## AUTH discovery

- Trusted catalogue remains independent from this split; all REV lifecycle
  actions remain unavailable.
- AUTH-09A/09B/09C, 09D-A, and 09D-B are merged. PR #148 merged 09D-A as
  `99ae4c963e53f317175dcb308b9e47c93ccf19ed` from reviewed head
  `9c5ef8a1feffd6324acfd947e67042921955320b`, establishing database-backed
  ActorProfile lifecycle status/provenance and migration
  `0026_actor_profile_lifecycle`.
- `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` merged through PR #153 at `8d5eb15b`
  from reviewed head `6a70b33f`. Migration `0027_contributor_foundation`
  supplies the exact field clean cut, ActorProfile FKs, reusable human-kind
  trigger function, active-human transaction revalidation, and regression
  evidence required by REV.
- AUTH-09E, AUTH-PREP, REV custody, AUTH-10 through 14, and matching feature
  activations remain unmerged. AUTH-13/14 contracts require later amendment for
  prepared revision/replacement facts and cannot be treated as current runtime
  gates.
- All 24 REV lifecycle actions remain unavailable. REV never registers,
  provisions, evaluates, or activates them.

## ART discovery

- ART v2 LocalStorage clean cut merged through PR #141 at `a10d901`, S3/MinIO
  preparation merged through PR #151 at `1b5422fc`, and admission/put-attempt
  foundation merged through PR #154 at
  `44f2467cedc266d2efe261119cfff436ac6b7715` from final head `c93f1a24`.
- PR #154 adds `0028_artifact_admission` and no Project/setup writer file, so
  the 02A1 writer inventory is unchanged by that merge. Provider execution,
  verification publication, recovery, routes, and product cutover remain later
  ART work.
- Current ART map does not schedule an exact lease-scoped review packet-read
  capability, review-evidence candidate/finalize capability, or server-derived
  stabilized Submission artifact digest. REV-03B, 07A/07B, 09A3/09A4, 10, and
  projection work remain blocked on exact owner chunks.
- REV must consume typed capability ports and never ArtifactStore, concrete
  adapters, provider references, scratch paths, or ART repositories.

## CON discovery

- CON-01 canonical specification/ADR is merged; CON runtime 02A onward remains
  proposed on trusted main.
- Any unmerged CON migration must rebase from the current head; REV consumes no
  sibling worktree or proposed revision number.
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
- Parent 02A failed L1 preimplementation review because it combined the entire
  project/setup writer graph, guide chronology, Task stamping, two migrations,
  and persistent coverage work. Split it into 02A1 fencing, 02A3 chronology,
  and 02A4 Task triplet before runtime. Keep later hidden 02A2 reactivation
  separate; 02A2 must merge
  before AUTH-12 evaluator/cutover/activation, not after an active action.
- Move historical admission scan to authorized reconciliation child 11C.
- Separate persisted phase execution denial from static router/AUTH membership
  and operational scheduler state.
- Keep active release docs and route registration together in 13C.

## Unknowns and owner actions

- AUTH must later amend AUTH-12/13/14 contracts; the contributor foundation
  gate itself is satisfied.
- ART must schedule/merge packet-read, review-evidence, digest, and projection
  capabilities.
- CON must merge its runtime foundations from the then-current migration head.
- Human must approve the two positive 02B duration defaults.

Until those facts are on trusted main, REV planning may continue but runtime
must stop at each affected gate.
