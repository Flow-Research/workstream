# Status: WS-REV-001 Review And Revision Lifecycle

## Current status

Trusted main is `cb9d5f9f9c311e644ed20a988c69843d3618a6b0`, which includes
the merged parent 02A planning split in PR #156, ART admission foundation PR
#154, and shared transactional outbox PR #155. Automated loop memory named
`WS-REV-001-02A1` behind an explicit-start
gate, and the user explicitly started that child on 2026-07-19. Current work is
the bounded L1 Project/setup publication-fence implementation. No migration,
model, schema, router, background-job, public API, authorization, policy-semantics, or
02A3 change is authorized.

The reconciled refresh confirmed sole Alembic head
`0029_shared_transactional_outbox`, the
literal 18-writer inventory, no ART-owned Project/setup writer, and a clean
dependency merge. Initial QA plan review failed closed on abstract race
fixtures; the repaired contract now defines each writer row, both acquisition
orders, PostgreSQL wait observation, independent AST inventory proof, remote
transaction boundaries, and structural setup-worker isolation. Senior/
architecture/reuse, QA/product/test-delta, and security/docs/CI plan tracks all
then returned PASS before application code changed.

## Trusted dependency truth

- Single Alembic head: `0029_shared_transactional_outbox`.
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
- CON-01 merged its specification and CON-02A shared transactional outbox
  persistence merged through PR #155, advancing the sole migration head to
  `0029_shared_transactional_outbox`. It changes no 02A1-owned Project/setup
  writer.
- Sibling AUTH/ART/CON status files contain stale post-merge wording. REV records
  actual merge facts but does not edit owner initiative memory.

## Plan-refresh results

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

- Separate 02A1, 02A3, and 02A4 starts after each predecessor merges. The AUTH
  contributor foundation gate is satisfied.
- Exact positive `review_preference_window_seconds` and
  `review_lease_duration_seconds` before 02B. Neither derives from `sla_hours`.
- Exact human Review revision-round counting, deadline anchor, and boundary
  before 09A1; checker retries are excluded unless a separate product/ADR
  amendment is explicitly approved.
- Exact merged AUTH-14 contract amendment before 09A4 must leave REV ownership
  of Submission revision-source columns/constraints intact and limit AUTH to
  public request acknowledgement, authorization cutover, and activation.
- Every later external owner dependency and child start as listed in the map.

## Stop condition

Publish only `WS-REV-001-02A1`, obtain the explicit human merge decision, let
automated memory record the merge, and stop. Do not start 02A3 automatically.
