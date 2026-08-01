# Plan: WS-XINT-003 REV-AUTH End-to-End Contract

## Approach

Deliver one reconciliation foundation followed by narrow feature-backed
activation waves:

1. Reconcile policy ownership, the complete catalogue, permissions, principal
   classes, fixed-service matrix, surface manifests, and planned availability.
2. Cut over review/revision policy configuration in two merge-safe steps. 02A
   adopts the existing tables as immutable/versioned REV records on the current
   migration head and removes the four unused legacy writer/construction
   callables while activating nothing. 02B adds the only public mutation routes
   and service, consumes AUTH PREP, appends through the sole internal repository
   primitives, records bounded authorization evidence atomically, and activates
   only the two policy ActionIds.
3. Activate concealed reviewer current-work, claim/release/preference, and timer
   services only after REV queue/lease behavior exists.
4. Amend XINT-002-07 into two ART-only owner waves: 07A is the only ActionId
   availability transition and activates packet materialization plus
   finding-slot evidence binding after lease readiness; 07B changes no ActionId
   availability and only extends the active binding evaluator to response slots
   after a human revision obligation exists. XINT-003 activates the
   corresponding human REV actions and never takes custody of ART actions.
5. Activate bounded `review.chain.read` after the packet/context owner wave.
6. Activate `review.decision` only after the complete hidden atomic
   Review/FinalAcceptance/CON composition exists.
7. Let XINT-002-05D activate shared human-review revision preparation/Submission
   actions, then let XINT-002-07B extend ART response binding after hidden REV
   obligation/preparation behavior exists. XINT-003-07 consumes both merged
   boundaries and separately activates contributor response authority.
8. Record the four missing privileged lifecycle/recovery actions as future 08R
   work. Keep their ActionIds unregistered until 08R, then activate
   Project Manager/Operator recovery and fixed service jobs with
   reason-bound least privilege and crossed-race proof.
9. Run complete conformance, then permit REV's single product-route release.

## Universal mutation protocol

Every durable mutation follows this order:

1. Verify the external token and resolve canonical actor/identity link, or
   resolve one fixed admitted service identity.
2. Perform cheap preflight authority before sensitive bytes or expensive work.
3. Prepare an opaque, non-serializable handle in the caller-owned root
   transaction, bound to actor/service, identity link where human, ActionId,
   request digest, idempotency key, session, and root transaction.
4. Lock AUTH authority first, then feature idempotency/lifecycle rows in the
   action's documented order.
5. Recompose exact current feature facts using typed feature-owned loaders.
6. Consume the handle once against the final resource context and stage bounded
   decision evidence.
7. Apply the protected REV/Task/Submission/CON/audit/outbox mutation and commit
   once. Provider I/O and projection occur only after commit where applicable.

Copied, serialized, forged, replayed, wrong-session, wrong-transaction,
wrong-action, wrong-actor/service, cross-project, cross-task, cross-submission,
cross-lease, cross-review, stale-policy, stale-packet, stale-predecessor, expired,
revoked, or already-consumed capabilities fail closed with no partial product
mutation.

## Read protocol

Reads still evaluate current authority and canonical feature scope.
Administrative queue-inspection lists filter before counts/cursors. Reviewer
context and chain reads require the exact
active lease and disclose only bounded metadata plus the current packet.
Historical artifact bytes are not implied by chain visibility. Reauthorization
is required before returning a replayed mutation result.

## Ownership model

- AUTH code contains no REV repositories or lifecycle branching.
- REV code contains no grant queries, token-role checks, or alternate policy
  evaluator.
- Typed feature contexts are composed beside their owning repositories and
  presented to AUTH through the established authorization interfaces.
- ART services execute byte materialization/binding under their own authority;
  they do not inherit reviewer, contributor, or uploader authority.
- CON participates flush-only in the caller transaction and never authorizes
  the reviewer.

## Policy ownership reconciliation

The existing policy persistence is adopted or migrated once; it is not
duplicated. REV-03P defines immutable/versioned policy semantics and validation.
AUTH-12D2 protects the two mutation routes and supplies authorization evidence.
02A must retire the unused `upsert_review_policy`, `upsert_revision_policy`,
`_review_policy_model`, and `_revision_policy_model` callables before 02B
introduces the sole active writer. The child contracts and both parent contracts
must remain synchronized.

## Policy mutation replay custody

02B generalizes the existing project-owned guide mutation replay boundary into
one project-mutation replay ledger/repository. The migration preserves existing
guide replay rows, renames the guide-specific model/table/constraints and
repository deliberately, and expands the closed action constraint only for the
two policy actions. GuideMutationService and ProjectPolicyMutationService share
that repository; neither owns an in-memory, alternate, or policy-only replay
store. This is a bounded project composition abstraction, not a generic service
locator.

## Verification strategy

- exact catalogue/permission/action/matrix and route/command parity;
- migration single-head, upgrade, downgrade/refusal, and direct-SQL proof;
- PostgreSQL concurrency barriers for every crossed authority/lifecycle race;
- property/table-driven prepared-handle denial matrices;
- atomic Review/FinalAcceptance/CON/audit/outbox fault injection;
- all-pairs fixed-service denial and Celery serialization scans;
- bounded read/redaction/concealment tests;
- focused coverage at or above 90 percent for changed subsystems;
- GitHub-hosted full suite preserving the repository-wide 78 percent floor;
- architecture, security, product/ops, QA, senior, reuse, docs, test-delta, and
  CI-integrity reviews as applicable.

## Alternatives rejected

Separate per-REV-chunk AUTH invention, direct REV grant reads, a generic review
resource context, a generic artifact download permission, and activation before
hidden behavior are rejected.

## Stop boundary

This planning amendment creates no runtime code and activates no action. 02A is
the only implementation-ready child. 02B remains non-implementable until 02A
merges and a current-main refresh freezes its exact migration and verification
commands. Chunks 03A through 09 remain planning skeletons. Planning completion
does not start the next child automatically.
