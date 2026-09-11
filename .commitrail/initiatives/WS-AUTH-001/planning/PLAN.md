# WS-AUTH-001 — Current pre-review activation plan

The [cross-owner dependency contract](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
owns current delivery order through `allow_review`. The
[preserved plan](../pre-cutover/PLAN.md) retains completed history; its broad
AUTH-13/14 cutovers are not additional implementation work.

- AUTH-12I/12J/12B2 are complete. POL-04B consumes their exact adapters.
- [AUTH-12F4](chunks/WS-AUTH-001-12F4-submission-policy-approval.md) follows
  hidden POL-05A approval/provenance and precedes POL-05B.
- [AUTH-12G](chunks/WS-AUTH-001-12G-post-submit-checker-policy-mutations.md)
  follows hidden POL-06A post-policy operations and precedes POL-06B.
- [AUTH-12H](chunks/WS-AUTH-001-12H-guide-activation.md) follows POL-07 and
  hidden CP07. It activates only the complete PROJECTS guide command.
- CP05 owns exact ContributionPolicy-action activation after merged CP04B.
- ARCH-03B owns task behavior and ARCH-03C owns its exact activation.
  [AUTH-13 is superseded](chunks/WS-AUTH-001-13-task-assignment-cutover.md).
- ARCH-04D alone activates post-submit materialization/output and CHECKERS
  execution/finalization after ARCH-04B/04B2/04C; historical AUTH-14 and XINT-06B
  cannot start in parallel. ARCH-03B/03C explicitly own task queue/read and
  pre-submit invalidation; downstream REV queue/reconciliation remains separate.

For 12F4/12G, use their current child contracts rather than the old storage model;
the current POL-05A/06A operations determine authoritative resource facts,
replay identity and separate downstream storage. AUTH consumes public facts,
never creates policy storage or mutates a finalized setup row. Each mutation
binds actor/link/grant or exact fixed service, project, operation/correlation,
compilation/component/approval identities, session and transaction. Test
cross-project, stale generation, substituted action/resource, revoked authority,
concurrent replay and rollback before activating the live adapter.

The bounded [task project-grant repair](../../../changes/task-project-grant-authorization.md)
replaces contributor claim/start/work-context authority, adds separate management
context and reasoned system-Operator start, and removes self-activated eligibility
and public JSON-packet Submission creation. Admission-backed creation stays hidden.
ARCH-03B/03C must reuse these exact actions and command owners while completing
ContributionPolicyVersion lineage, ready queues, remaining projections and durable
invalidation. Do not restore eligibility or register replacement aliases.

## WS-AUTH-001-OUTBOX-01 — unavailable dispatcher contract

Disposition: Planned. L1. Depends on merged shared outbox persistence and
AUTH's fixed-service/admission/PREP foundations. This is one AUTH-owned change:
register proposed action/permission `outbox.dispatch`, fixed identity
`workstream.outbox.dispatcher`, its singleton matrix row and closed
claim/invoke/finalize resource/PREP contracts while keeping availability
planned. Allow AUTH catalogue/contracts/parity and focused tests only; no
dispatcher or feature behavior. Inputs include event identity, claim generation,
lease, action/resource digest, session and transaction. Prove absent/foreign
identity, copied claim, wrong generation and every unrelated feature action
deny. CON-02B consumes this unavailable contract to build hidden mechanics.
Claim, invocation and finalization each obtain fresh transaction-bound
authority. No PREP handle or authority-bearing object survives a commit,
lease wait, handler/provider I/O or serialization. After invocation, finalize
revalidates the committed claim generation and current dispatcher authority;
an old pre-invocation allow cannot authorize that later write.

## WS-AUTH-001-OUTBOX-02 — exact dispatcher activation

Disposition: Planned. L1. Depends on OUTBOX-01 and the exact hidden CON-02B
manifest. Allow AUTH evaluator/composition/parity and integration proof;
prohibit outbox behavior rewrites or feature-handler authority. Activate only
dispatcher mechanics after claim/lease/recovery proof. Prove provisioned and
missing-identity cases, expiry/revocation, wrong event/generation, rollback,
and denial of ART, CHECKERS and TASK actions. A registered handler separately
obtains its own feature authority. Missing provisioning denies work, not app
startup or the administrative provisioning route.

Both boundaries require focused architecture/security/QA review and affected
CI/docs review. Human focus: a dispatcher can deliver a request but cannot
authorize its product effect. These current contracts replace no product
owner and create no new planning-permission gate.

## TASK post-submit acceptance custody

ARCH-04E2 owns the proposed `task.post_submit.route` contract for the fixed
`workstream.task.post_submit_router`. Its false/pass consequence reuses the
[shared acceptance sequence](../../../../docs/spec_review_lifecycle.md#finalacceptance),
not a new FinalAcceptance or CON materialization action. The typed resource
binds the exact committed claim, immutable Submission, current checker
run/generation/result and outputs, locked false ReviewPolicy, assignment and
contribution-policy lineage, and intended derived effects. Consume fresh
transaction-bound authority; checker/dispatcher allows cannot substitute.
Acceptance must satisfy the canonical false-readiness contract above, including
rejection of any applicable approved `human_review` requirement disposition.
CP07/12H enforce ARCH-04F remediation availability and valid scoped controller
generation as activation prerequisites, not additional route-resource facts;
runtime still consumes the shared lifecycle fence required by that contract.
True permits human admission only. Activation of the false consequence waits
for the hidden REV/CON/TASK atomicity and terminal-currentness proofs; the
service never receives human `review.decision` or generic contribution access.
