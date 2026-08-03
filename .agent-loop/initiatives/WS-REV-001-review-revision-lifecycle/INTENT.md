# Intent: WS-REV-001 Review And Revision Lifecycle

## Problem being solved

Current main proves project policy, task, Submission, checker, and authorization
foundations but has no human review runtime. Workstream cannot yet turn a final
current CheckerRun recommendation of `allow_review` into an authorized,
immutable, traversable judgment and revision history.

## Why this work matters

Review is the certification boundary between submitted work and trusted
ContributionRecord facts. It must prevent self-review, duplicate claims,
mutable judgment, hidden history loss, and partial contribution effects while
remaining independent of AUTH, ART, CHECKER, TASK, and CON internals.

## Current behavior

- AUTH `WS-XINT-003-02A` through `02D` are merged through PR #257 at
  `3479ee71`. Policy identity/mutation, the complete unavailable REV catalogue,
  six fixed service principals, and closed typed REV authorization contracts
  exist.
- The sole Alembic head is `0049_rev_auth_readiness`.
- All REV lifecycle actions remain planned or unavailable; no review route,
  queue, lease, Review, revision, or recovery behavior exists.
- ART owns the Submission artifact custody chain and reviewer packet bytes.
  Its final submission/checker and reviewer-packet handoffs remain future work.
- CON owns ContributionRecord, award, and fulfillment behavior. Its typed
  review participant remains a later integration dependency.

## Target behavior

```text
final current CheckerRun = allow_review
+ existing immutable Submission
+ exact verified ART binding facts
        -> one REV queue entry
        -> server-selected offer
        -> one active reviewer lease globally
        -> lease-bounded packet and chain
        -> immutable Review + findings/resolutions
        -> accept | needs_revision | reject
        -> revision replay or FinalAcceptance
        -> reviewer ContributionRecord for every Review
        -> submitter ContributionRecord only from FinalAcceptance
```

All prior Submissions, Reviews, findings, responses, and resolutions remain
traversable. Future adjudication may consume that history but is not part of
v0.1.

## Design chosen

Build the complete hidden REV core behind stable AUTH `02D` contracts. Keep
external intersections behind typed ports and wire them only after their owners
merge exact interfaces. Persistence and pure lifecycle rules may proceed before
ART packet materialization or CON decision participation is available.

The first implementation child is a REV-only persistence foundation. It does
not admit checker results, expose routes, activate actions, call ART, or create
contributions.

## Boundaries preserved

- REV begins at final current `allow_review`; it never creates or repairs a
  Project Guide, Task, Submission, CheckerRun, or artifact binding.
- AUTH owns ActorProfile/grant evaluation, PREP, evidence, fixed principals,
  catalogue, and availability. REV locks its own facts and composes the exact
  final `review_contracts.py` model.
- ART owns bytes, verified bindings, materialization, provider behavior, and
  packet-byte delivery. REV owns only packet membership and lifecycle meaning.
- TASK owns task/assignment/Submission transitions through typed
  caller-transaction participants; REV owns decision orchestration.
- CON owns ContributionRecord, policy, awards, and fulfillment through typed
  flush-only operations. REV owns Review, FinalAcceptance, audit/outbox staging,
  and the single transaction commit.
- PostgreSQL is canonical. Projections are derived and retryable.

## Expected risks

- Cross-subsystem interfaces may arrive after core persistence.
- Queue, claim, expiry, decision, and revocation races require database proof.
- Historical plans use obsolete names, owners, and dependencies.
- Large combined migrations or public-route work would be unreviewable.
- A contribution or artifact outage must never fabricate an adverse decision.

## What must not change

- Decisions remain exactly `accept`, `needs_revision`, and `reject`.
- Self-review remains forbidden and reviewer capacity remains one active lease.
- Existing Submission is the version identity; no `SubmissionVersion` table.
- Findings and responses are text/metadata records in v0.1; uploaded review
  evidence remains separate future intent.
- Checker-caused remediation remains distinct from human revision.
- Reject affects only the exact task/assignment and creates no submitter
  contribution.
- No adjudication, reputation mutation, frontend, marketplace, or provider
  expansion enters this initiative.

## How this will be proven

Database constraints, migrations, independent-session concurrency tests,
AUTH-contract parity, typed-port architecture scans, fault injection, focused
changed-subsystem coverage at or above 90 percent, GitHub-hosted full coverage
at or above 78 percent, and final real-API lifecycle drills.

## Human decisions required

No decision blocks the first persistence child. Before human revision episode
work, the human must approve exact revision round counting, deadline anchor,
and inclusive/exclusive deadline semantics. Every later implementation child
still requires its own explicit start.
