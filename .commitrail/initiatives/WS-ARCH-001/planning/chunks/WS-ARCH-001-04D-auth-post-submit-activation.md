# Chunk Contract: WS-ARCH-001-04D AUTH Post-Submit Activation

Status: ARCH-04D1 canonical custody is Complete; ARCH-04D2 is Complete under
the [bounded authority record](../../WS-ARCH-001-04D2.md).
Risk: L1. Outcome: ARCH-04D2 activates exact fixed-service materialization,
evaluator execution and finalization boundaries, replacing the historical
XINT-06B/broad AUTH-14 design. Output ingestion and binding remain unavailable
until a real registered checker produces output files.

ARCH-04D2 is the sole current activation contract; XINT-06B and broad AUTH-14
are historical custody references, not parallel work. Materialization PREP
precedes storage access; final-result PREP binds the accepted output after
I/O. Fixed-service registrations and resource facts must come from the exact
04B/04C manifest, not a generic checker or artifact permission.

Allowed: AUTH catalogue/matrix/evaluator/PREP adapters, delivery composition,
focused AUTH/XINT tests, boundary ledgers and evidence/status. Not allowed:
new authorization protocol, human checker authority, generic artifact reads,
REV actions, TASK transition ownership or serialized prepared handles.

## Canonical ART lineage activation prerequisite

[ARCH-04D1](../../WS-ARCH-001-04D1.md) delivers this database prerequisite.
Migration 0009's ART-owned scalar validator compares all nine material facts with
one consumed Submission admission/binding/content/verified-replica lineage.
Every terminal run with non-null material is checked, including infrastructure
failures after materialization. Completed results still require material;
`material_unavailable` requires null. Current replica health does not rewrite
historical identity. Upgrade locks out writers across preflight/installation,
preserves valid retained rows and refuses unprovable rows without backfill.

04D1 proves independent foreign admission/replica/manifest substitutions and
transaction rollback with controlled phase participants. It does not prove real
AUTH finalization audit custody. ARCH-04D2 supplies that atomicity proof and
real authorization tests for exact service activation. No CHECKERS runtime
private ART query, alternate store or compatibility path is introduced.

## CHECKERS service manifest

ART's existing actions cover materialization, output ingestion and binding;
none authorizes a CHECKERS run/result write. Only materialization is needed by
the current zero-output catalogue. Register one exact
fixed identity `workstream.checker.post_submit` with two action/permission
pairs: `checker.post_submit.execute` for attempt execution/pre-I/O admission
and `checker.post_submit.finalize` for final-result persistence. Register their
typed contexts, static matrix and exact admitted phases through the existing
AUTH/PREP service after the hidden 04C behavior manifest. No human or outbox
dispatcher receives these service-only permissions. The existing ART
materializer/output identities retain their separate actions; do not collapse
them into this evaluator identity.

Finalization requires fresh authority after I/O, exact current request/fence,
accepted-result digest, canonical material and the current empty output tuple. The preflight
allow does not authorize final persistence. Operator terminal retry retains
its separately governed recovery action and cannot impersonate ordinary
execution. Negative proof covers each service attempting the other's actions,
request substitution, revocation between calls and complete final rollback.

Acceptance: service, action, resource digest, session, transaction, approved
generation, Submission/binding and checker identities are exact. Resource
facts also bind 04A/04C evaluation-request identity, server-owned
generation, post-plan hash, phase and attempt identity, and the final result
digest where available. Execution/finalization also bind CHECKERS worker-lease
generation separately from outbox claim and evaluation generation. They cannot
authorize a different request or expired worker on the same
Submission. Stale,
cross-resource, mismatched replay, copied-handle or revoked requests detected
before I/O deny before protected side effects. Fresh validation after I/O
suppresses final-current result and routing writes if authority or lineage
changed; it cannot undo earlier authorized reads/evaluator calls. Exact valid
replay validates the stored phase-specific authorization receipt under fresh
authority and returns the same identity without duplicate audit or product
effects; it never borrows an earlier allow in place of current authority. Execute/finalize evidence commits
atomically with its protected write. Materialization evidence commits before
provider access and may remain after a subsequently failed authorized read. Verify catalogue/database parity,
PostgreSQL races, boundary validators, Ruff and hosted coverage. Required
reviews: authorization architecture, security, product/ops, QA, senior, CI and
test delta.

The [04D2 record](../../WS-ARCH-001-04D2.md) defines current files, strict
execution/materialization facts, lock ordering, stored-receipt replay, migration
head, commands and reviewers. No database transaction or PREP handle crosses
provider/evaluator I/O. A race after an authorized read cannot undo that read;
fresh currentness and authority prevent the stale worker publishing a result.

## Merge state

- ARCH-04D1: `Complete`.
- ARCH-04D2: `Complete`.
