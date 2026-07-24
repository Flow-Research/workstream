# Status: WS-ART-001 Immutable Artifact Storage

## Completed Foundation

Planning and the artifact foundation merged through PR #97 and PR #101. The
AWS-first object-storage amendment and typed adapter clean cut merged through
PRs #120, #127, #129, #141, and #151. Durable admission, put attempts,
verification/publication, recovery idempotency, and hidden Operator operations
merged through PRs #154, #159, #174, and #177 (`WS-ART-001-02D`).

The current v0.1 provider direction remains AWS S3 in production, MinIO for
local/CI protocol proof, and LocalStorage for development/focused tests. Flow
Node and R2 remain deferred. Completed objects have no physical deletion path.
AUTH's owner reconciliation merged through PR #140 as
`d541521`; PLAN2 preserves AUTH ownership and proposes no availability edit.

## Cancelled Work

`WS-ART-001-03` received a signed implementation start on current history, but
mandatory preimplementation review rejected the combined contract before any
runtime edit. The user authorized cancellation, and signed automation run
`30100940860` recorded `stopped_after_cancel` on 2026-07-24. The rejected
contract combined guide byte ingest, binding, materialization, setup recovery,
migration, and inactive AUTH dependencies without a safe executable boundary.

## Current Planning Reconciliation

`WS-ART-001-PLAN2` is planning-only. It incorporates the human-approved
submission invariant:

```text
one outer ZIP
-> bounded private scratch inspection and canonical manifest
-> exact/semantic unchanged rejection
-> mandatory platform and locked Project Guide prechecks
-> one existing ArtifactStore admission and complete read-back verification
-> one immutable Submission binding
-> the same bytes checked, reviewed, accepted, recorded, and delivered
```

There is no candidate store, temporary provider retention, promotion copy,
physical deletion, second recovery aggregate, speculative capacity increase, or
competing `SubmissionVersion` table. Reviewers attach a decision plus
note/findings to the
exact `Submission`; contributors answer `needs_revision` with another complete
ZIP and immutable Submission.

## Next Proposed Chunk

After this planning package merges, `WS-ART-001-03A` is the only immediate ART
successor. It adds hidden guide-source byte ingest through the existing artifact
preparation/admission/verification path. It requires a separate signed start and
does not activate its own AUTH action.

## Gate

Planning evidence and all required internal reviewer tracks must pass before a
PR. The planning merge starts no successor. Every implementation chunk retains
its separate signed start, exact AUTH activation sequence, internal review, CI,
CodeRabbit, human checkpoint, and automated merge-memory stop.
