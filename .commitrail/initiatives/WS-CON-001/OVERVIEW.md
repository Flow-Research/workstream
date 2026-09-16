# WS-CON-001 — Contribution and conditional compensation

Current pre-review work follows the [cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
and the [capability ledger](../../../docs/roadmap_status.md).

- Disposition: Planned
- Completed boundary: hidden policy behavior, exact Finance Authority, CP06 selected-policy validation and CP07 hidden guide activation/binding.
- Intent: record completed authorized reviews and accepted submissions as
  immutable ContributionRecords and optional
  project-policy-driven compensation awards without coupling lifecycle truth to
  an economic provider.
- Next usable boundary: remaining ARCH-03B queues and actor-specific projections
  after completed ARCH-03B1 detached metadata and CP08 lineage
  and minimal writers, ARCH-03A internal guide context,
  [CP07 activation/binding](../WS-ARCH-001/WS-ARCH-001-CP07.md) and
  [AUTH-12H live authority](../WS-AUTH-001/WS-AUTH-001-12H.md), before task readiness.
- Governing sources: `docs/spec_contribution_compensation.md`,
  [`CONFORMANCE.md`](CONFORMANCE.md), code, migrations, and tests.
- Preserve: exact policy-version lineage, no claim-time drift, decimal-string
  quantity integrity, atomic REV/CON effects, and no runtime reputation
  projection in v0.1.

## Delivered

- Shared outbox, adapter-binding persistence and hidden lifecycle behavior,
  contribution-policy persistence and hidden draft/publication/retirement
  behavior, and shared lifecycle-audit participation are merged.
- [CP07A](../WS-ARCH-001/WS-ARCH-001-CP07A.md) aligns authority-before-resource
  locking and the database audit vocabulary for existing binding actions.
- Finance Authority adapter-binding and five policy actions are active through
  explicit AUTH composition; public policy routes remain unavailable. ContributionRecord, award, dispatch, fulfillment, and
  public CON behavior are not yet complete.

## Remaining v0.1 sequence

Use the [current cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
for remaining integration and CP09 work; CON does not create a second policy/binding lane.

[CP05](../WS-ARCH-001/WS-ARCH-001-CP05.md) delivered exact authorization for
the hidden policy behavior.

1. Completed CP06 validates the expected version against the active policy's current
   published selector for new guide activation, without reselecting existing
   frozen work; CP07 supplies hidden PROJECTS
   activation/binding, and AUTH-12H supplies its live manager authority. ARCH-03A completes the internal context port;
   CP08 delivers lineage fields and existing Task/Assignment/Submission writers together.
   ARCH-03B retains queues, invalidation and broader projections. CP09 removes the replaced legacy
   economic path only after all consumers are replaced, including CHECKERS and
   public Submission cutover; it does not block canonical `allow_review`.
2. Add CON-03C ContributionRecord/CompensationAward persistence after the
   REV-04B shared source/FinalAcceptance FK foundation, then the CON-07 atomic
   submitter participant. These shared pieces do not require live human
   decision/queue/lease behavior. The locked ReviewPolicy boolean
   `human_review_required` defaults true; false permits authorized automated
   acceptance without a Review or reviewer contribution. Both use the same
   FinalAcceptance/submitter-contribution participant and applicable awards.
   The existing shared REV-12A/CON fence/ordinal foundation precedes this
   operation; later drain and fulfillment surfaces do not block it.
   Automated acceptance must not require live human-review infrastructure;
   see the [canonical source, authority and transaction contract](../../../docs/spec_review_lifecycle.md#finalacceptance).
3. Shared dispatcher CON-02B is pulled forward before canonical task authority
   invalidation and post-submit routing, independently of ContributionRecord/
   award persistence. AUTH-OUTBOX-01 supplies its unavailable contract and
   AUTH-OUTBOX-02 activates its proven mechanics. Add fulfillment,
   reconciliation and product reads only after
   their exact AUTH service identities and actions exist.

## CON-02B current dispatcher contract

Disposition: Planned. Risk: L1. Consume
[AUTH OUTBOX-01/02](../WS-AUTH-001/planning/PLAN.md#ws-auth-001-outbox-01--unavailable-dispatcher-contract).
Shared outbox owns hidden claim/lease fencing, typed handler registry,
invoke/finalize, bounded retry/dead-letter/replay and drain observation. Reuse
the existing outbox rows and caller-session append service; do not implement
contribution, compensation, checker, TASK or provider behavior here.
Allowed files are the shared outbox module, its composition/worker registration,
bounded configuration and focused tests/docs. Each handler receives immutable
event/claim facts, validates the committed claim through a public port and
returns a typed outcome without mutating outbox rows. Commit claim before
handler invocation; hold no row lock across handler/provider I/O.

Prove independent-session lease expiry, stale-worker fencing, crash before and
after invoke/finalize, redelivery, exact replay, retention and non-false-zero
drain observation. Dispatcher identity cannot execute any feature action and
registration refuses handlers without their own authority manifest. Production
stays unavailable until AUTH-OUTBOX-02. Focused architecture/security/QA and
changed workflow/test reviewers inspect these proofs, using real PostgreSQL/
Redis and unchanged hosted coverage. The original detailed dispatcher record
remains in the archive; its old directory paths and relative sequencing do
not override this current contract.

## Preserved history

ReviewPolicy setting history: [product-builder handoff](../../changes/pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
