# Plan: WS-XINT-003 REV-AUTH End-to-End Contract

## Approach

Deliver the dependency using the same model proven by WS-XINT-002: complete
AUTH readiness up front, then use narrow feature-backed activation waves:

1. Reconcile policy ownership, the complete catalogue, permissions, principal
   classes, fixed-service matrix, surface manifests, and planned availability.
2. First cut policy persistence and every downstream lock to immutable policy
   identity in 02A without runtime activation. Then cut over review/revision
   policy configuration through one persistence path in 02B: REV owns
   semantics; AUTH-12D2 owns authorization and PREP consumption.
3. Before REV begins its full lifecycle implementation, complete the AUTH side
   once: register all approved v0.1 REV actions as unavailable, provision the
   exact fixed-service principals and static matrix, and publish closed typed
   PREP request/resource contracts for every approved human, Project Manager,
   Operator, and service action. This foundation must activate nothing and must
   contain no REV lifecycle loaders or rules.
4. REV then implements its complete lifecycle against those stable fail-closed
   contracts. Each later XINT activation connects an exact merged REV composer
   to AUTH and changes availability only after crossed-state proof; it may not
   discover or add another action, permission, principal, or protocol.
5. Activate concealed reviewer current-work, claim/release/preference, and timer
   services only after REV queue/lease behavior exists.
6. Let XINT-002-07A activate packet materialization only after lease readiness.
   Keep ART review-evidence binding planned and unavailable; the approved v0.1
   reviewer flow stores a decision plus note/findings, not an uploaded reviewer
   artifact. XINT-003 never takes custody of ART actions.
7. Activate bounded `review.context.read` and `review.chain.read` together after
   the packet/context owner wave.
8. Activate `review.decision` only after the complete hidden atomic
   Review/FinalAcceptance/CON composition exists.
9. Let XINT-002-05D activate shared human-review revision preparation/Submission
   actions after hidden REV obligation/preparation behavior exists. Any future
   response-artifact upload requires separate approved REV intent.
10. Activate Project Manager/Operator recovery and fixed service jobs with
    reason-bound least privilege and crossed-race proof. Their ActionIds and
    principals were already installed unavailable by the AUTH foundation.
11. Run complete conformance, then permit REV's single product-route release.

## Dependency rule

AUTH readiness is an input to REV implementation; REV implementation is an
input only to action activation. No future REV chunk may stop to request a new
AUTH catalogue value, permission mapping, fixed identity, static matrix row, or
authorization protocol already covered by this initiative. If such a need is
discovered, return to this plan rather than adding it inside a REV chunk.

The front-loaded AUTH contracts carry stable identifiers, enums, digests,
bounded facts, and opaque PREP handles. They do not query REV tables, create a
Review or ReviewLease, route work, decide lifecycle meaning, or expose a route.
REV owns canonical loaders/composers and all product behavior. Availability
remains planned until the exact AUTH adapter and REV composer pass integrated
denial, concurrency, and atomicity proof.

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
The implementing chunk must explicitly retire overlapping legacy writer paths
and update both contracts together.

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

This planning amendment creates no runtime code and activates no action. Chunks
02A through 09 are non-implementable planning skeletons until a current-main
refresh replaces every file/command placeholder with exact boundaries and the
user explicitly requests that chunk. Planning complete does not start runtime
work.
