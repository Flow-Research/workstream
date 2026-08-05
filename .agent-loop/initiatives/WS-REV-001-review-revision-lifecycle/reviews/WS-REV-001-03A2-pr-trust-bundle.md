# PR Trust Bundle: WS-REV-001-03A2

## Goal and boundary

Persist immutable REV-owned lease attempts and enforce reviewer-preference
actor integrity. The change consumes ART submission/version lineage, AUTH actor
profiles, and CON's canonical published policy-version identity without
performing any upstream operation or adding claim, review, revision, decision,
FinalAcceptance, or contribution behavior.

## Design

- `ReviewLease` records exact queue/project/task/Submission/version, human
  reviewer, frozen same-project policy version, generation, and timestamps.
- Partial unique indexes allow one active lease per queue and one globally per
  reviewer.
- Deferred constraints permit either safe write order while requiring the
  queue's `leased` state and active pointer to match the active lease at commit.
- Database guards enforce human actors, published policy identity, immutable
  attempt facts, terminal provenance, delete/truncate refusal, and preference
  integrity.
- The repository only adds and flushes a supplied lease; it does not authorize,
  select, commit, or update the queue.

## Proof

The focused PostgreSQL queue/lease suite passes 20 tests with 98.70 percent REV
branch coverage. Migration round-trip, upgrade preflight, populated downgrade,
real two-session capacity races, schema fingerprint, lane integrity, Ruff,
stale wording/contracts, Markdown links, and diff integrity pass. All required
internal reviewer tracks pass with no actionable findings.

## Human review focus

Review the deferred queue/lease graph, partial uniqueness, canonical human and
published-policy guards, immutable terminal history, migration safety, and the
absence of callable review behavior. GitHub Actions must run the full suite and
repository coverage. Only the user may authorize merge.
