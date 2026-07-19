# Chunk Contract: WS-REV-001-02 - Locked Review Policy And Task Lifecycle Alignment

## Status

Split before runtime implementation after required L1 plan review. No backend,
migration, or persistence-test work may execute against this parent contract.

The user explicitly started parent `WS-REV-001-02` on 2026-07-18, then confirmed
that REV could continue planning and test design only while AUTH-09D-A and the
separate contributor-field foundation remained unmerged. Both dependencies are
now merged; parent 02 remains non-executable because its child boundaries and
separate human-start gates still control runtime work.

## Parent initiative

`WS-REV-001` - Review And Revision Lifecycle

## Goal

Bound the locked guide, review-policy, task-lifecycle, assignment, and existing
Submission alignment work without adding review queues or creating overlapping
AUTH schema ownership.

## Why the split is required

The original contract combined three independently risky PostgreSQL boundaries:

- Project Guide activation sequencing and publication locking;
- locked ReviewPolicy/RevisionPolicy plus dormant task/assignment lifecycle
  compatibility; and
- existing Submission attribution, predecessor integrity, context stamping, and
  finalized-row immutability.

Each boundary requires its own migration preflight, direct-SQL constraints,
concurrency proof, downgrade rules, focused coverage, and human review. The
combined L1 change was not credibly PR-sized.

## Child chunks

| Chunk | Title | Boundary |
|---|---|---|
| `WS-REV-001-02A` | Guide Chronology And Task Locking Split | Non-executable planning parent for 02A1 Project/setup fencing, 02A3 guide chronology, and 02A4 Task triplet screening. |
| `WS-REV-001-02B` | Locked Review Policy And Dormant Task Lifecycle Compatibility | Make guide-bound review/revision policy exact and immutable and add non-executable terminal task/assignment schema compatibility without fabricating Review. |
| `WS-REV-001-02C` | Submission Attribution, Context, And Immutable Lineage | Bind each existing Submission to its exact assignment and canonical contributor, enforce same-task immediate-predecessor lineage, stamp guide identity, and protect finalized rows. |

## Dependency order

```text
AUTH-09D-A and AUTH contributor foundation merged
-> WS-REV-001-02A planning split
-> WS-REV-001-02A1
-> WS-REV-001-02A3
-> WS-REV-001-02A4
-> human approval of the two duration defaults recorded in 02B
-> WS-REV-001-02B
-> WS-REV-001-02C
-> WS-REV-001-03
```

AUTH migration `0026` owns profile lifecycle and merged migration `0027` owns
the contributor foundation. REV assigns no later migration identifier in parent
planning. Every executable child refreshes from trusted `main` and allocates
only the then-current single Alembic successor at its own start.

## Preserved boundaries

- AUTH owns the clean cuts from both retired contributor-identity storage fields
  to `contributor_id` and the reusable database-backed ActorProfile human-lineage
  foundation. REV consumes the merged result and never recreates it.
- `Submission` remains the only versioned submission identity.
- TaskAssignment stores only `task_id`; it receives no guide/context duplicate.
- No child adds a Review, queue, lease, finding, FinalAcceptance, public review
  route, AUTH implementation, ART implementation, CON behavior, or synthetic
  reject.
- `accepted`, `rejected`, `cancelled`, `completed`, and `blocked` are dormant
  compatibility states here. Their Review-driven service transitions land only
  with the owning immutable Review/decision chunks.
- The reject Review foreign key is owned by later Review persistence and is not
  added by 02B.

## Planning proof

The future test cases are specified in
`TEST_DESIGN_WS-REV-001-02.md`. The plan must retain explicit tests for unsafe
migration refusal, direct SQL, concurrency, downgrade refusal, and absence of
premature Review-driven effects.

## Stop condition

Stop at this split record. Do not implement a child until its exact dependency
SHAs, migration head, child-specific human decisions, contract review, and
separate human start are recorded.
