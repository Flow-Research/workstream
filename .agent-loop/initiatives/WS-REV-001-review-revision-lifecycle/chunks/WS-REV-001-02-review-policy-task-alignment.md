# Chunk Contract: WS-REV-001-02 - Locked Review Policy And Task Lifecycle Alignment

## Status

Split before runtime implementation after required L1 plan review. No backend,
migration, or persistence-test work may execute against this parent contract.

The user explicitly started parent `WS-REV-001-02` on 2026-07-18, then confirmed
that REV may continue planning and test design only. Runtime remains blocked
until AUTH-09D-A merges and AUTH subsequently merges its separately reviewed
contributor-field foundation from the then-current migration head.

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
| `WS-REV-001-02A` | Project Guide Activation Sequence And Publication Locking | Allocate immutable per-project activation chronology, stamp Task guide identity, and publish one internally consistent guide generation. |
| `WS-REV-001-02B` | Locked Review Policy And Dormant Task Lifecycle Compatibility | Make guide-bound review/revision policy exact and immutable and add non-executable terminal task/assignment schema compatibility without fabricating Review. |
| `WS-REV-001-02C` | Submission Attribution, Context, And Immutable Lineage | Bind each existing Submission to its exact assignment and canonical contributor, enforce same-task immediate-predecessor lineage, stamp guide identity, and protect finalized rows. |

## Dependency order

```text
AUTH-09D-A merged
-> AUTH-owned contributor-field foundation reviewed and merged
-> WS-REV-001-02A
-> human approval of the two duration defaults recorded in 02B
-> WS-REV-001-02B
-> WS-REV-001-02C
-> WS-REV-001-03
```

AUTH currently owns migration `0026` for profile lifecycle. REV assigns no
migration identifier in planning. Every child refreshes from trusted `main` and
uses the then-current single Alembic head only after the contributor foundation
has merged.

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
