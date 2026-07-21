# WS-AUTH-001-10 PR Trust Bundle

## Chunk

`WS-AUTH-001-10` - Project Qualification And Contributor Role Grants Planning

Merge intent: `.agent-loop/merge-intents/WS-AUTH-001-10.json`

## Goal And Human-Approved Intent

Turn the approved independent project-role design into executable, separately
gated implementation contracts without shipping a migration or runtime surface.
The user approved the 10A/10B/10C split and asked to start this planning chunk.

## What Changed And Why

- Recasts AUTH-10 as a planning-only parent and declares 10A as its exact
  same-initiative successor.
- Defines 10A for migration `0031`, immutable qualification/grant truth,
  availability-neutral evidence parity, and five planned catalogue rows.
- Defines 10B for the three privacy-safe candidate/list/detail reads and a
  signed, filter-bound pagination codec.
- Defines 10C for PREP-bound issue/revoke mutations, deterministic locking,
  idempotency, audit/invalidation, replay, failure atomicity, and live API proof.
- Reconciles D32 and the canonical reference specification with independent
  submitter, reviewer, and adjudicator grants.

The split was chosen because schema/evidence, privacy-sensitive reads, and
multi-principal mutations have different risks and proof boundaries. One
combined implementation PR was rejected during L1 plan review.

## Scope And Product Behavior

Only initiative planning, chunk contracts, the canonical reference spec, one
merge intent, review evidence, and this trust bundle change. No Workstream
product behavior, migration, action availability, route, CI workflow, or test
changes in this parent.

## Acceptance Proof And Test Delta

- Stale authorization documentation: PASS.
- Markdown links: PASS.
- Merge-intent validation: PASS.
- Diff integrity: PASS.
- All nine required internal review tracks pass exact planning SHA
  `ca52fd6a6c51f78b3e3a10faf77f4ab235843ad2` after fixes.
- No tests were added, modified, removed, skipped, or weakened because this is
  a planning-only parent. Each child owns focused local tests; GitHub owns its
  full suite and coverage proof.

## CI Integrity

Coverage floors, lint/typecheck commands, workflow behavior, dependencies, and
test selection are unchanged. Child contracts preserve GitHub ownership of the
full sharded suite, aggregate 78 percent coverage, authorization 90 percent
coverage, API E2E, and Agent Gates.

## External Review And Remaining Risks

CodeRabbit and GitHub checks are pending publication. Remaining implementation
risk is intentionally isolated into the three children: migration privacy and
refusal in 10A, read disclosure/cursors in 10B, and mutation concurrency/replay
in 10C. None may start from this PR alone.

## Follow-Up And Human Review Focus

After this parent merges, trusted automation must name 10A and a fresh explicit
start event must activate it. Review the independent-role model, exact child
boundaries, 10A planned-versus-active distinction, lock ordering, privacy-safe
read schemas, replay state machine, and the absence of runtime or migration
changes in this parent.

## Human Merge Ownership

The agent may publish and repair this branch but may not merge it. Only the user
may approve this specific PR for merge. Trusted-main automation owns signed
post-merge memory generation.
