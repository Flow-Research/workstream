# Chunk Contract: WS-AUTH-001-12F4 - Unified Pre-Submit Approval Activation

Durable disposition: Complete. Risk: L1.

Adopted implementation record: [AUTH-12F4](../../WS-AUTH-001-12F4.md).
POL-05A is delivered; this contract supplies its authorization prerequisite
for subsequent POL-05B public composition.

## Goal

Activate the Project Manager approval action, complete-proposal read and
setup-wide correction authority with exact PREP/evaluator
composition required by POL-05B to publish the approved artifact,
effective-policy, and pre-submit chain.

## Allowed files

AUTH catalogue/kernel/prepared/runtime/API authorization composition, narrow
POL approval adapter/resource context, focused authorization/integration tests,
AUTH/POL specifications, and initiative memory.

## Not allowed

Agent calls, product compiler/lifecycle implementation, policy body writes,
post-submit projection/approval, checker execution, Celery, ART, submission
intake, migration of product columns, or approval of a 12F3-only draft.

## Acceptance

- All three actions are active for the covered human Project Manager:
  `project.submission_artifact_policy.approve`,
  `project.guide_compilation.review_package.read`, and
  `project.guide_compilation.correction.request`.
  Every service and unrelated human denies.
- Complete-proposal read (`project.guide_compilation.review_package.read`) maps to
  `project.guide.manage`, requiring a current exact-project human Project
  Manager grant and a new exact compilation resource contract. Operator, Audit,
  service and foreign-project grants deny. The package contains guide-derived
  prose but excludes raw document payloads, runtime handles and replayable
  references. It grants no approval or correction power; existing status-only
  diagnostic authority is insufficient.
- Setup correction (`project.guide_compilation.correction.request`) maps to
  `project.guide_compilation.request` for the covered human Project Manager.
  It binds the exact known finalized predecessor, safe correction digest and
  unique successor request. It cannot retry an uncertain provider outcome or
  authorize fixed-service execution. POL-05A owns the immutable correction
  operation and new-generation allocation; the existing execution action
  separately governs the eventual compilation call.
- Resource/PREP binds project/guide/source/setup generation, immutable
  compilation/result plus artifact/pre/post component hashes, both catalogue
  snapshots, target draft, current approval identity/hash/provenance,
  compiler/plan versions, operation, request,
  idempotency, actor/link/grant, session, and root transaction.
- The complete unified result, including post-submit proposal and capability
  gaps, exists before approval can prepare or consume.
- POL-05A supplies the hidden product locks, compilation, append-only approval
  operation, replay and caller-transaction contract; POL-05B wires that same
  implementation live. Neither AUTH nor POL-05B invents another mutation owner.
  AUTH evaluates and persists bounded decision evidence atomically through the
  existing participant; it does not implement a competing compiler.
- Revocation, stale/mixed generation, changed component/catalogue/approval
  hash or provenance, mismatched replay,
  copied/wrong handle, or transaction/session mismatch denies with no product
  mutation or allowed evidence.
- Exact valid replay returns the same operation after fresh authority checks;
  the finalized setup row/receipt remains unchanged on approval or replay.

## Verification and review

AUTH all-pairs, PREP integrity, full-result-before-approval, stale-hash, POL
integration, API metadata, hosted coverage, and impact-routed architecture, security, QA and product/operations reviews, plus tracks affected by the actual diff. Human focus:
narrow human activation over a complete immutable proposal.
