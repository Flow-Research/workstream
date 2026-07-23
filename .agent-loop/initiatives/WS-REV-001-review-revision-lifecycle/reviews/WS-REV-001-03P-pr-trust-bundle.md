# PR Trust Bundle: WS-REV-001-03P

## Chunk

`WS-REV-001-03P` - Review And Revision Policy Persistence.

## Goal

Persist the immutable REV-owned policy facts required by later review routing,
leases, decisions, and human revision work, without implementing those later
lifecycle stages.

## Human-approved intent

REV starts only after `allow_review`, consumes the existing Submission and
artifact set, records complete traceable review/revision history in later
chunks, and never absorbs Project Guide, Task, AUTH, ART, or CON ownership.

## What changed and why

Migration 0034 replaces ambiguous legacy policy columns with explicit review
preference/lease, finding-evidence, revision-limit/deadline, and provenance
facts. Legacy values remain private and losslessly downgradeable until one
atomic conversion. Models, schemas, repository/service mapping, active docs,
and focused tests now agree with that database contract.

## Design chosen

Separate table-specific triggers make policy rows immutable, serialize every
insert/update with the exact guide row, reject runtime legacy claims, and permit
only atomic legacy-to-canonical conversion. Downgrade locks all three involved
tables and refuses canonical facts or unreconstructible archives before DDL.

## Alternatives rejected

- No mutable published policy or delete path.
- No runtime fallback defaults for migrated incomplete rows.
- No combined queue, lease, Review, decision, revision, or contribution work.
- No AUTH-owned actor schema or ART/Submission behavior.
- No lossy downgrade.

## Scope control and product behavior

The change is limited to the contract's policy persistence, mapping, docs, and
proof-only compatibility exceptions. Canonical decisions remain exactly
`accept`, `needs_revision`, and `reject`. No review lifecycle transition is
activated by this PR.

## Acceptance criteria proof

Direct SQL proves canonical shape, provenance, private archives, immutable
identity/context, update/delete refusal, runtime-insert denial, atomic
conversion, downgrade refusal, and lossless legacy round-trip. Eight real
PostgreSQL races prove both policy tables and both write operations serialize
with guide publication in both lock orders.

## Tests/checks run

Focused migration, Project, Task, and artifact tests passed. Alembic has one
head, Ruff passed all changed backend paths, stale wording and Markdown links
passed, 100 agent-gate tests passed, and diff integrity passed. Full backend
tests and coverage are delegated to GitHub Actions as instructed by the user.

## Test delta and CI integrity

Tests add constraints, downgrade, deterministic waiter, legacy compatibility,
archive privacy, and immutable snapshot proof. Existing compensation and ART
assertions remain intact. No workflow, package script, skip, xfail, coverage
floor, or assertion was weakened; CI must preserve 78 percent repository-wide
coverage and prove at least 90 percent for the materially changed subsystem.

## Reviewer results

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, CI integrity, and circuit breaker all PASS on code
candidate `b9501b31565370306aea168ff4c218a2880e6c0b`. The earlier
`35531df254c6b25726d666a5e89eda997b97d792` candidate predates external CI
fixture repairs.

## External review

PR #195's first run passed preflight, Agent Gates, and shards 2 and 4. It failed
API E2E, shards 1 and 3, and therefore the aggregate test gate. Repairs align
the API policy request fixture, six migration-head expectations, and one ART
fixture's policy-before-publication ordering without changing assertions or
product behavior. Focused failing tests, Ruff, diff integrity, and exact-SHA
internal review pass. CodeRabbit's green context explicitly said it could not
start a review because its review limit was reached; it is not review evidence.
Fresh current-head GitHub Actions and an actual CodeRabbit review remain
required before merge.

## Remaining risks and follow-up work

Later queue, lease, Review chain, decision, revision, FinalAcceptance, and CON
composition remain deliberately unimplemented. After merge, loop memory may
name same-initiative successor 03A, but 03A requires a separate explicit signed
start and a fresh current-main dependency check.

## Human review focus

Review the trigger invariants, downgrade refusal/reconstruction, eight race
cases, legacy API privacy, strict REV boundary, and preservation of Task and
ART compatibility assertions.

## Human merge ownership

Only the user may approve and merge this specific PR. Do not merge with a
pending/failed current-head GitHub or CodeRabbit check or an unresolved
actionable comment. Merge does not start 03A.
