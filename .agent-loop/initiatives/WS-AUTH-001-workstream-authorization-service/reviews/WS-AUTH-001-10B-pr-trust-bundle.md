# WS-AUTH-001-10B PR Trust Bundle

## Chunk

`WS-AUTH-001-10B` — Project Role Grant Read Planning Parent

Merge intent: `.agent-loop/merge-intents/WS-AUTH-001-10B.json`

## Goal and human-approved intent

Protect entrusted submitter and project-owner authorization data by separating
durable cross-replica read abuse control from privacy-sensitive disclosure. The
user approved the 10B1/10B2 split after required review found the inherited
10B contract unsafe to implement as written.

## What changed and why

- D33 makes 10B planning-only and declares 10B1 as its only successor.
- 10B1 extends the existing PostgreSQL counter with one locked
  `authorization_read` scope, independent capacity settings, an unattached
  dependency, migration rollback safety, and hosted 90 percent coverage.
- 10B2 attaches that control exactly once to three reads and owns strict minimal
  responses, canonical resource scope, audited concealment, signed keyset
  cursors, exact three-action activation, and hosted API proof.
- 10C follows only after 10B2 and retains all mutation/PREP work.

## Scope and product behavior

This PR changes planning/process artifacts and one merge intent only. It adds no
migration, route, runtime behavior, test, workflow, public documentation, or
action activation. Authored `STATUS.md` is unchanged because signed automation
owns live state.

## Evidence and review

Exact commit `25b6ae134e3e3db4350fbcbb5c7cfeaa9e261044` passed all nine required
review tracks against trusted main `f2aa57a4`. Stale scans, Markdown links,
merge-intent validation, and diff integrity pass. No test or CI threshold was
changed or weakened.

## Remaining risks and follow-up

10B1 must prove migration locking and cross-replica counters before any read
surface exists. 10B2 must prove rate-before-lookup, indistinguishable public
404 behavior with correct evidence semantics, no counts, minimal schemas,
cursor replay resistance, and exact action/OpenAPI activation. Each child needs
its own protected start, implementation review, GitHub full suite/coverage,
CodeRabbit review, and human merge approval.

## Human review focus and merge ownership

Review the 10B1/10B2 boundary, migration `0032` ownership, action-aware
concealment, cursor threat model, hosted coverage requirements, and exact
successor order. The user retains approval for this specific PR and merge.
