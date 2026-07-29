# WS-XINT-002-04A PR Trust Bundle

## Intent

Activate only `artifact.guide_source.ingest` for an active covered Project
Manager grant through the shared opaque, transaction-bound PREP protocol.

## Design

The route obtains a request-local human PREP adapter. Preparation locks the
actor, exact identity link, and matched Project Manager grant before scratch or
body-byte intake. ART later locks the project, draft guide, source snapshot, and
source item, computes byte facts, and consumes the same handle before capacity,
put intent, or provider I/O. The allowed decision digest and protected database
mutation commit in one root transaction.

## Scope

- Activates only guide-source ingest and assigns activation custody to
  `WS-XINT-002-04A`.
- Adds the existing ingest permission only to Project Manager policy.
- Adds one typed guide-ingest resource context and prepared-kernel path.
- Completes ART-owned project/draft-guide/snapshot/item locking.
- Keeps guide read, guide binding, submissions, reviews, and generic downloads
  unavailable.

## Tests and evidence

- Catalogue availability/custody and exact role-policy matrix.
- Exact grant permission/project/`FOR UPDATE` request.
- Opaque handle forgery, lineage/request mismatch, complete final fact
  projection, and reuse denial.
- Real PostgreSQL proof for wrong-project, revoked-link, revoked-grant, locked
  lineage, non-draft lineage, successful admission, and zero denied side
  effects.
- Existing canonical PREP tests retain copied/serialized, cross-session/root,
  wrong-action/resource, concurrent consume, and replaced-transaction proof.
- The audit active-action set and independent custody/count fixtures prove the
  planned-to-active transition exactly; the first hosted failure caught their
  stale values and the correction preserves their strict equality checks.
- Transaction tests prove nested PREP scopes deny, successful caller-owned roots
  commit once, failed roots roll back once, and consume failures close and deny.
- Local static and focused non-database checks passed; hosted database coverage
  and full-suite evidence are pending on the exact PR head.

## CI integrity

No workflow, test runner, skip, coverage pragma, threshold, or failure-handling
configuration changes are included. A hosted 89.94 percent artifact-foundation
result was corrected by covering eleven additional production statements.
Required thresholds remain global 78 percent and affected
authorization/artifact subsystems at least 90 percent.

## Review result

All required internal tracks completed. Valid planning, test, wording, and
fixture findings were addressed. Remaining notes are low risk and documented in
the internal review record.

CodeRabbit's two exact documentation findings after retargeting to `main` were
fixed and recorded in `WS-XINT-002-04A-external-review-response.md`. The final
incremental review and exact-head hosted Backend result remain required.

## Human review focus

Confirm PM-only policy, canonical system/project grant coverage, pre-byte
preparation, final ART-owned draft lineage locks, final resource-context digest,
denial atomicity, and that only guide ingest becomes active.
