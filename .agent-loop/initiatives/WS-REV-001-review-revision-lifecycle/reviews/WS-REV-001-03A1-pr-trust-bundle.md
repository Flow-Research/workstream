# PR Trust Bundle: WS-REV-001-03A1

## Chunk

`WS-REV-001-03A1` — Queue And Admission Persistence.

## Goal

Add the smallest hidden REV-owned persistence foundation for one exact
reviewable Submission queue identity and one idempotent admission operation.

## Human-approved intent

Start at a completed, current `allow_review` CheckerRun; consume the existing
Submission/version without changing upstream owners; stop before selection,
leases, Reviews, revisions, FinalAcceptance, or contributions.

## What changed and why

- Added `ReviewQueueEntry` and `ReviewAdmissionIdempotencyRecord` models,
  schemas, and caller-transaction repository operations.
- Added Alembic revision 0050 with exact lineage/admissibility guards,
  immutable identity, replay constraints, delete/truncate protection, and
  populated downgrade refusal.
- Registered the models and schema fingerprint, added focused PostgreSQL tests,
  and clarified the data-model boundary.

This separates stable queue/admission identity from the later concurrency and
policy-version concerns of REV-owned lease persistence.

## Design chosen

One immutable queue row references the existing project, Task,
Submission/version, and admitting CheckerRun. A separate pending-to-committed
idempotency row records replay identity and binds only to the exact matching
queue. PostgreSQL is the final invariant boundary; repository methods flush but
never commit the caller's transaction.

## Alternatives rejected

- No checker completion hook or automatic admission.
- No route, backlog read, reviewer selection, claim, lease, or active-lease
  placeholder.
- No upstream row changes, AUTH lookup, ART locator/bytes, or CON state.
- No historical backfill or fabricated checker fact.
- No destructive downgrade after either protected table contains a row.

## Scope and product behavior

This PR changes only the reviewed 03A1 contract, REV initiative evidence/status,
REV models/repository/schemas, migration, metadata registration, focused tests,
data-model docs, and one schema-v2 merge intent. It exposes no product API or
review lifecycle action.

## Acceptance criteria proof

Database constraints and triggers prove one queue per Submission, exact
project/task/Submission/version/checker lineage, current completed
`allow_review`, server-owned queue age/generations, immutable identity,
open/preferred storage without lease shape, exact replay namespaces/digest, and
pending-to-committed admission binding. Direct tests cover every refusal path
and isolated downgrade refusal for each protected table.

## Tests, test delta, and CI integrity

Focused isolated PostgreSQL migration and persistence tests pass. Focused
branch coverage for the complete new REV package passes the 90 percent floor.
Ruff, the stale review-contract scan, changed Markdown links, Alembic one-head,
and diff integrity pass. No existing test, assertion, skip, workflow, package
script, global 78 percent baseline, or CI gate was weakened. GitHub Actions will
run the full suite and repository coverage.

## Reviewer results and external review

Architecture, senior engineering, QA/test, product/ops, security/auth, docs,
CI integrity, reuse/dedup, and test-delta tracks pass after resolving replay,
server-stamping, scope, coverage, constraint, and downgrade-test findings.
GitHub Actions and CodeRabbit are pending until publication.

## Remaining risks and follow-up

The queue preserves the checker admission fact at write time; it does not own
or constrain later upstream state. Digest syntax remains locally repeated
rather than introducing a cross-owner abstraction in this chunk. 03A2 remains
a separately approved successor and must not begin from this PR.

## Human review focus

Review exact cross-owner lineage, current `allow_review` enforcement, fresh-ID
replay semantics, server-stamped queue age, no lease/API shape, protected
downgrade behavior, and absence of AUTH/ART/CON ownership leakage.

## Human merge ownership

Only the user may approve and merge this specific PR. Do not merge while any
current-head GitHub or CodeRabbit check is pending or failed, or while an
actionable review comment remains unresolved. Merge does not authorize 03A2.
