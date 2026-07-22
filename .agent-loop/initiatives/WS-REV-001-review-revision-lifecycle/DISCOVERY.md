# Discovery: WS-REV-001 Review And Revision Lifecycle

## 2026-07-22 Boundary Correction

Complete rereading of the checksum-bound WS-REV Markdown, all 52 pages of its
PDF companion, the active `docs/spec_review_lifecycle.md`, and ADR 0010 confirms
that REV begins after a final current checker `allow_review` admission and must
preserve the proven Project Guide/Task/Submission/Checker intake spine. ADR 0010
requires REV revision preparation to consume a stable active-guide identity; it
does not transfer Project Guide setup or activation ownership to REV.

The derived PLAN2/02A sequence incorrectly converted that dependency into REV
implementation ownership. Proposed 02A1 Project/setup fencing, 02A3 activation
chronology, 02A4 general Task stamping, and 02A2 guide reactivation are therefore
retired as REV chunks. Any still-needed capability must be specified as an
external owner handoff. The unmerged 02A1 runtime candidate was reverted before
publication.

After merging current main at `14fa4316f7d984f2176657bfafd2a2dae56f944e`,
the sole migration head is `0033_authorization_read_rate_control`. AUTH PR #175
changes no REV product boundary. Signed loop memory remains stopped with retired
02A1 named next; PLAN3 must replace that successor through reviewed merge memory
before 03P can receive a signed start.

## Baseline

Discovery was refreshed read-only from trusted main
`14fa4316f7d984f2176657bfafd2a2dae56f944e`. PLAN3 makes no backend/runtime
changes.

## Current boundary facts

- The repository remains FastAPI/Python with async SQLAlchemy 2.x, Alembic,
  Pydantic, and PostgreSQL; the sole head is
  `0033_authorization_read_rate_control`.
- `Submission` remains the owner-supplied versioned submission entity. REV must
  consume its exact finalized identity, immediate-predecessor lineage, Task and
  contributor facts, and submitted artifact membership; any missing invariant
  or typed read contract is work for that owner.
- Checker completion remains owner-supplied. REV admission may consume only one
  durable final/current `allow_review` result; it may not produce or repair a
  CheckerRun.
- ART recovery is present through migration `0032_artifact_recovery_attempts`,
  but each future REV artifact read/evidence need still requires an exact merged
  typed owner contract and proof at that chunk's signed start.
- AUTH PR #175 and migration `0033_authorization_read_rate_control` add
  authorization-read rate control without transferring reviewer identity,
  permission, or lifecycle ownership to REV.
- CON remains the owner of contribution records. REV later composes its typed
  participant so every committed Review creates one reviewer contribution and
  only accept creates the submitter accepted-submission contribution.
- REV owns ReviewPolicy/RevisionPolicy (03P), queue/lease persistence (03A/03B),
  admission/routing (05A/05B), immutable Review/finding/resolution chains,
  human revision replay, FinalAcceptance, and decision orchestration.

## Historical PLAN2 discovery snapshot — archival and void

> Every section and ownership/chunk statement below this heading records the
> superseded PLAN2/02A investigation only. It is not current dependency truth,
> an owner assignment, a human-decision request, or implementation authority.
> D28, PLAN3, `CHUNK_MAP.md`, and the proposed 03P/03A contracts control.

## Historical backend snapshot

- FastAPI/Python, async SQLAlchemy 2.x, Alembic, Pydantic, PostgreSQL.
- Historical single Alembic head: `0028_artifact_admission`.
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
- The historical PLAN2 proposal observed that checker-caused remediation is
  supported but accepted ADRs scope controlled
  guide rebase/preparation to human Review revision. The plan must preserve a
  distinct CheckerRun-rooted N+1 path rather than treating it as legacy or
  silently applying human RevisionPolicy/D6 behavior. Current Submission storage
  lacked immutable causal CheckerRun lineage. It incorrectly assigned 02C to add
  and backfill `remediation_source_checker_run_id`; under PLAN3, any still-needed
  lineage is an external Checker/Submission owner requirement that REV consumes.
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
