# Plan: WS-XINT-002 ART-AUTH End-to-End Contract

## Design

Deliver the dependency in two front-loaded AUTH foundations followed by thin,
evidence-gated activation waves:

1. Reconcile the complete v0.1 catalogue and static service matrix once.
2. Close the PREP-to-ART operation interface once: durable mutation requests
   carry opaque prepared authority, while exact feature contexts remain with
   their evidence-backed activation chunks.
3. Activate fixed internal recovery services before any durable provider work.
4. Activate guide ingest/use only after the matching hidden ART behavior.
5. Activate initial contributor preparation, then atomic Submission/binding
   consumption, then checker-remediation and human-review revision variants as
   separate reviewable gates.
6. Activate checker materialization/output only after exact checker behavior.
7. Activate reviewer packet and evidence binding only after both ART and REV
   provide their hidden typed facts and lease/revision guards.
8. Run end-to-end conformance and crossed-state proof.

Registration is deliberately complete up front. Activation remains separate
because AUTH cannot safely allow an action until the protected implementation,
resource composer, and denial tests exist. Each activation chunk may only
connect a previously registered action to an exact merged feature manifest and
change its availability; it may not invent another action or permission.

## Canonical action and permission set

### Human-facing actions

| ActionId | PermissionId | Authority |
|---|---|---|
| `artifact.guide_source.ingest` | `artifact.guide_source.ingest` | covered Project Manager grant |
| `artifact.submission_bundle.prepare` | `submission.create` | active assigned contributor |
| `submission.create` | `submission.create` | fresh active assigned contributor |
| `review.context.read` | `submission.read_for_review` | exact active reviewer lease |
| `review.finding_evidence.ingest` | `review.decision` | active reviewer lease and exact review context |
| `review.finding_response_evidence.ingest` | `submission.create` | contributor with exact revision obligation |

### Fixed-service actions

| ActionId | PermissionId | Service identity |
|---|---|---|
| `artifact.verification.execute` | `artifact.verification.execute` | `workstream.artifact.verifier` |
| `artifact.pending_work.scan` | `artifact.pending_work.scan` | `workstream.artifact.scheduler` |
| `artifact.put_attempt.resolve` | `artifact.put_attempt.resolve` | `workstream.artifact.put_resolver` |
| `artifact.guide_source.read` | `artifact.guide_source.read` | `workstream.artifact.guide_reader` |
| `artifact.guide_source.binding.create` | `artifact.binding.create` | `workstream.artifact.binding` |
| `artifact.submission.binding.create` | `artifact.binding.create` | `workstream.artifact.binding` |
| `artifact.pre_submit.checker_input.materialize` | `artifact.checker_input.materialize` | `workstream.artifact.materializer` |
| `artifact.post_submit.checker_input.materialize` | `artifact.checker_input.materialize` | `workstream.artifact.materializer` |
| `artifact.checker_output.write` | `artifact.checker_output.write` | `workstream.artifact.checker_output` |
| `artifact.checker_output.binding.create` | `artifact.binding.create` | `workstream.artifact.binding` |
| `artifact.review_packet.materialize` | `artifact.review_packet.materialize` | `workstream.artifact.materializer` |
| `artifact.review_evidence.binding.create` | `artifact.binding.create` | `workstream.artifact.binding` |

The existing bounded Operator actions remain unchanged. Fixed recovery services execute
recovery; Operators request retry/reconciliation and inspect bounded state.
There is no generic artifact-download action.

Submission preparation has three closed context variants under the same action:
initial submission; checker remediation rooted in the exact final
`needs_revision` CheckerRun; and human-review revision rooted in the exact
revision obligation. Checker remediation records the server-derived
`remediation_source_checker_run_id`, immediate same-task predecessor, existing
locked task context; it has no inherited `allow_review`, ReviewFinding
response, revision preparation, human revision deadline/round consumption,
reviewer contribution, or synthetic human actor.

## Universal durable-boundary protocol

Every durable ART/product mutation must:

1. authorize before accepting expensive or sensitive bytes;
2. prepare authority inside the caller-owned root transaction;
3. lock AUTH actor/link/grant or fixed-service authority first;
4. lock and recompose exact feature facts through typed feature-owned ports;
5. consume the opaque capability against the final resource context;
6. stage bounded decision evidence and the protected mutation atomically;
7. commit once before provider I/O; and
8. obtain fresh authority for each later binding or product mutation.

Copied, serialized, replayed, cross-session, cross-action, cross-resource,
replaced-transaction, revoked, stale, or already consumed handles deny.

## Ownership rule

AUTH evaluates authority but does not load feature rows or encode product
lifecycle. Chunk 02 closes durable ART mutation ports around the existing
opaque prepared handle and removes the obsolete upload-session interface.
Each activation chunk then defines its closed typed composer/loader in the
owning feature module, binds its proof to the same session and root
transaction, and owns its locks and invariants. ART orchestrates bytes and
receives only opaque prepared handles plus typed decisions; it never imports
AUTH repositories.

## Verification

- focused PostgreSQL catalogue/migration/PREP/concurrency suites per chunk;
- static route/command/action and service-matrix parity gates;
- stale-action and forbidden-import scans;
- 90 percent coverage for materially changed backend subsystems;
- hosted GitHub Actions full backend suite preserving the 78 percent global
  floor; and
- security, architecture, QA, product/ops, senior, CI, docs, reuse, and test
  delta review as applicable to each L1 chunk.
