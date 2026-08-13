# Chunk Contract: WS-ARCH-001-04E Canonical Allow-Review Manifest

Status: non-executable planning skeleton after 04D. Risk: L1. Outcome: the hidden admission-backed
Submission automatically dispatches post-submit checking and exposes one
durable current routing fact; an exact `allow_review` manifest becomes the REV
entry dependency.

Allowed: TASK owner-local dispatch/projection code and public API, delivery
composition, focused cross-module integration tests, boundary ledgers,
capability/status docs and exact evidence. Not allowed: REV queue writes,
reviewer behavior, CON behavior, public 02I route cutover, legacy-path claims,
or TASK-owned checker decisions.

Acceptance: one end-to-end test proves approved guide -> authorized assignment
-> verified admission -> immutable Submission/binding -> final current checker
result -> `allow_review`. The manifest explicitly binds the task in its exact
pre-review/evaluation state; immutable Submission id/version; assignment,
contributor and predecessor; admission id; ART binding, content, replica,
digest and byte count; final completed current CheckerRun; no unresolved
blocking failure under the locked post-submit policy; and
`routing_recommendation = allow_review`. It also carries the exact
`WorkstreamTask.locked_contribution_policy_version_id`, the exactly equal
`TaskAssignment.submitter_contribution_policy_version_id`, and locked
review/revision policy lineage needed by later REV and CON consumers. The
version was the same-project, published, complete, binding-valid immutable
version selected at guide activation and locked before task claimability; the
manifest never reselects it and later policy publication cannot alter the task,
assignment, Submission, or downstream lease.

Replay, revocation, stale guide/policy generation, stale assignment, replaced
binding, non-current run, cross-project/resource, wrong service, wrong session,
wrong transaction, and concurrent duplicate execution all deny. Every denial
proves zero provider reads, checker mutations, TASK routing transitions, REV
admissions, and duplicate Submission, binding, dispatch, run, or routing rows.
The only permitted denial evidence contains the canonical denial reason plus
request and correlation identifiers; it commits atomically with its denial
outbox operation and contains no product mutation or allowed-decision fact. No
REV admission occurs in this chunk. Verify real
API/database/Celery/MinIO integration, recovery
and concurrency tests, all boundary validators, Ruff and hosted coverage.
Required reviews: architecture, authorization security, product/ops, QA,
senior, reuse, CI, docs and test delta. Human focus: whether this exact merged
manifest is sufficient to let REV-05A begin.

Final checker outcomes other than `allow_review` remain hidden and fail closed
for routing in 04E. Before public 02I, a separate executable child must install
contributor-readable checker-remediation lineage for final needs-revision
checker results without creating Review, ReviewFinding, or
RevisionContextPreparation records.

Before implementation, replace this skeleton with a current-main contract that
enumerates exact files, commands, migration head and reviewers.

## Merge state

- Outcome on merge: `planned`
