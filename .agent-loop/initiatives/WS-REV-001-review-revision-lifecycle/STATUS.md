# Status: WS-REV-001 Review And Revision Lifecycle

## Current status

On 2026-07-22 a complete reread of the canonical Markdown and PDF specification
identified that the 02A family crossed the REV ownership boundary. REV begins
only when the current finalized checker result is `allow_review`; it consumes
the existing Submission and the same submitted/verified artifact set. Project
Guide setup, activation, Task intake, and upstream publication fencing belong to
their owning subsystems. REV reports gaps in those handoffs and does not repair
them. The attempted 02A1 runtime candidate was reverted in full.

`WS-REV-001-PLAN3` is proposed planning-only work, not canonically active. It retires
02A/02A1/02A2/02A3/02A4/02B/02C as REV implementation authorization. The first
future REV chunk is 03P: REV-owned ReviewPolicy/RevisionPolicy persistence.
Canonical start requires the signed `Loop Memory Explicit Event` workflow on
exact current main; chat and local work are not start evidence.

The historical text below records the superseded PLAN2/02A state and is not
current implementation authority. Trusted main at that time was `44f2467c`, which additionally
includes ART admission foundation PR #154 after REV PLAN2 PR #150, AUTH-09D-B
PR #152, and `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` PR #153. The user explicitly
started parent 02A on 2026-07-19. L1 preimplementation review returned FAIL
before runtime edits because the contract combined three separately reviewable
database/concurrency boundaries. That attempted split is now retired.

## Historical dependency snapshot

Current trusted main is `92b8a7aa813c5914d8191547b62eb3823a37a140`
with sole Alembic head `0032_artifact_recovery`. The bullets below describe the
older PLAN2 snapshot and are not current runtime proof.

- Single Alembic head: `0028_artifact_admission`.
- TaskAssignment and Submission expose canonical `contributor_id` with
  ActorProfile foreign keys and human-kind database guards.
- All 24 REV lifecycle action dependencies remain unavailable.
- AUTH-09D-A merged through PR #148 at
  `99ae4c963e53f317175dcb308b9e47c93ccf19ed` with reviewed head
  `9c5ef8a1feffd6324acfd947e67042921955320b`. Its ActorProfile lifecycle
  status/provenance and direct-SQL guards are trusted dependencies.
- The contributor foundation merged through PR #153 at `8d5eb15b` from reviewed
  head `6a70b33f`, with migration `0027_contributor_foundation`, final reviewed
  code candidate `0ca5a632`, and successful Backend, Agent Gates, and CodeRabbit
  checks. Its field clean cut, human lineage, and active-human transaction
  revalidation satisfy the former external 02A gate.
- ART admission/put-attempt foundation merged through PR #154 at `44f2467c`
  from final head `c93f1a24`, advancing the sole migration head to
  `0028_artifact_admission`. It changes no Project/setup writer and does not
  supply review packet-read, review-evidence candidate/finalize, or
  server-derived Submission artifact-digest capability.
- CON-01 merged its specification. CON runtime chunks 02A onward remain
  proposed on trusted main. Any unmerged CON migration must rebase from the
  then-current head before it is consumable.
- Sibling AUTH/ART/CON status files contain stale post-merge wording. REV records
  actual merge facts but does not edit owner initiative memory.

## Superseded PLAN2/02A record

This section is retained solely as historical evidence. Every ownership or
start statement in it is void under D28 and PLAN3.

- Parent 02A is a non-runtime split record. 02A1 owns the complete shared
  Project/setup writer fence, 02A3 owns guide chronology/canonical approval, and
  02A4 owns Task triplet screening.
- Current runtime rejects an already-active activation candidate. 02A3 names
  no-write active-repeat success as explicit additive behavior rather than
  incorrectly describing it as existing behavior.
- Proposed 02A2 owns prepared-authorized, `If-Match` protected superseded-guide
  reactivation after AUTH-PREP and AUTH-12. This preserves backward rebase
  without broadening the legacy public route.
- Existing oversized parent contracts are non-executable split records. Only
  the children in `CHUNK_MAP.md` may later receive implementation contracts.
- Chunk 08 is pure contract/validation only. Chunk 10 remains the first canonical
  Review/FinalAcceptance/CON transaction.
- Controlled revision preparation remains task-owned and rooted in an exact
  human `Review(needs_revision)`. Checker-caused `needs_revision` remains a
  distinct supported CheckerRun path, keeps existing task context, and never
  fabricates Review/finding/reviewer contribution or consumes human rebase/D6.
- Limit/deadline exhaustion cannot be repaired around; only exact D6 close may
  terminate that frozen human revision episode.
- Persisted release phase denies command execution. It does not unregister
  routers, change AUTH action availability/static membership, or replace
  scheduler operations.

## Canonical lifecycle

- Every valid reviewer decision appends immutable Review history; findings and
  later resolutions are also immutable.
- Every decision creates reviewer `completed_review` through CON.
- Accept alone creates immutable FinalAcceptance, accepts Task/completes exact
  assignment, and creates submitter `accepted_submission` from that fact.
- Needs revision creates no FinalAcceptance/submitter contribution and atomically
  appends the Review-rooted task-owned initial preparation.
- Reject blocks the exact reviewed Submission assignment and rejects Task; it
  creates no FinalAcceptance/submitter contribution.
- Checker needs revision atomically records the final CheckerRun transition with
  the Task's existing locked context and creates no Review, preparation, or CON
  record. Corrected N+1 persists the unique server-derived
  `remediation_source_checker_run_id`; later human N+1 instead persists its
  preparation ID, never both.
- Adjudication and reputation mutation remain deferred and unimplemented.

## Human-owned gates

- Start 03P only through the signed workflow after this reviewed plan merges.
- Start 03A only after 03P and after its current-main refresh proves every exact
  `allow_review`, Submission, artifact, and reviewer owner handoff.
- Exact human Review revision-round counting, deadline anchor, and boundary
  before 09A1; checker retries are excluded unless a separate product/ADR
  amendment is explicitly approved.
- Exact merged AUTH-14 contract amendment before 09A4 must leave REV ownership
  of Submission revision-source columns/constraints intact and limit AUTH to
  public request acknowledgement, authorization cutover, and activation.
- Every later external owner dependency and child start as listed in the map.

## Stop condition

Complete the PLAN3 boundary correction and stop. Do not implement runtime code.
Do not resume any 02A-family, 02B, or 02C chunk. After PLAN3 merges, await a
signed explicit start on exact current main before implementing 03P.
