# Chunk Contract: WS-REV-001-03A2 — Lease And Preference Persistence

## Status

Planning skeleton. Refresh only after 03A1 merges; do not start automatically.

## Parent initiative

`WS-REV-001` — Review And Revision Lifecycle.

## Goal

Persist ReviewLease attempts and preferred-routing state with database-enforced
active-capacity invariants, without implementing claim, release, decline, or
timer behavior.

## Why this chunk exists

Lease uniqueness and preference chronology form a separate high-risk
concurrency boundary from queue identity.

## Risk class and SLA

L1 database concurrency; no expedited SLA.

## Allowed files

Refresh exact review model/repository/migration/test paths from post-03A1 main.

## Not allowed changes

No routes, AUTH evaluation, claims, transitions, timers, packet manifests,
Review decisions, ART/CON calls, or action activation.

## Acceptance criteria

- One active lease per queue entry and one globally per human reviewer through
  PostgreSQL partial uniqueness.
- Completed attempts are immutable and retain reviewer, queue, policy-freeze
  reference slots, database timestamps, generation, and close provenance.
- Preference state preserves immutable queue age separately from availability
  time and lease expiry.
- Canonical ActorProfile FKs and human-kind guards prevent service identities
  occupying reviewer fields.
- No behavior is callable and every lifecycle action remains unavailable.

## Verification commands

Freeze exact migration, direct-SQL, concurrency, coverage, Ruff, stale-doc, and
GitHub full-suite commands at start.

## Required reviewers

Architecture, security/auth, product/ops, QA/test, senior engineering,
reuse/dedup, docs, test-delta, and CI integrity.

## Human review focus

Partial uniqueness, immutable attempts, actor kind, timer separation, and no
claim behavior.

## Stop conditions

Merge and stop before packet persistence or claim behavior.
