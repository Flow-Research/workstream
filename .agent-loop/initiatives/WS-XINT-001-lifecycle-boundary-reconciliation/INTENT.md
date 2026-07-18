# Intent: WS-XINT-001 Lifecycle Boundary Reconciliation

## Problem being solved

The AUTH, ART, REV, and CON initiatives were planned in parallel and use
inconsistent language for authorization activation, feature ownership, artifact
custody, contribution completion, combined contributor roles, and service
runtime admission. The runtime boundaries are mostly sound,
but the plans can still direct separate agents toward dual ownership or circular
activation dependencies.

## Why this work matters

These four initiatives meet in the same critical transaction paths. Ambiguous
ownership could authorize an action before its behavior exists, let feature code
manufacture authority, make ContributionRecord creation depend on an unrelated
artifact projection, or let one initiative mutate another initiative's state.

## Current behavior

- AUTH owns the closed permission/action catalogue and deny-by-default kernel.
- ART owns immutable artifact storage and is still building inactive provider,
  admission, verification, recovery, and product capabilities.
- REV and CON remain planning-only in their dedicated worktrees.
- Several active plans still say a feature chunk "activates" its own action even
  though the approved direction gives activation custody to AUTH.
- The current CON plan makes a separate contribution-evidence artifact a hard
  dependency of ContributionRecord creation.

## Target behavior

Every cross-initiative capability follows one order:

```text
AUTH planned registration
-> feature-owned hidden behavior and canonical resource composition
-> AUTH evaluator integration and activation
-> explicit joint release gate
```

ART, REV, and CON own their records, lifecycle guards, and typed capabilities.
AUTH owns identity, grants, the typed static service-action matrix, evaluators,
decision evidence, activation custody, and availability. Core
ContributionRecord creation consumes immutable Review and Submission facts
through a CON participant and has no
synchronous ART capability or provider dependency. It may retain an already
stabilized submission artifact digest as lineage without calling ART.

`ContributionPolicyVersion` is the upstream award-eligibility policy. The
version frozen on `TaskAssignment` or `ReviewLease` decides whether a resulting
`ContributionRecord` is unpaid or creates immutable money and/or project-points
`CompensationAward` rows. Only after that decision do separate downstream
adapters handle money payment requests/settlement or project-points fulfillment.

Project contributor authority uses independent exact-project `submitter`,
`reviewer`, and `adjudicator` grants; one human may hold all three rows, but any
one can be revoked without changing another. Adjudication actions remain
unavailable until WS-REV defines the lifecycle and AUTH activates exact
adjudication actions. Fixed service ActorProfiles use a separate AUTH
runtime-admission path and exact static action matrix, never human grants.

## Design chosen

- `ActionOwner` means AUTH activation custodian, not feature/resource owner.
- Feature/resource ownership is documented independently in typed handoffs.
- Mutations use one caller-owned transaction with AUTH authority locked first,
  feature rows locked second, final typed facts recomposed, one final decision,
  and one explicit commit.
- Reads use request-scoped AUTH decisions and feature-owned canonical loaders.
- Cross-initiative behavior remains hidden until both behavior and AUTH
  activation are merged and the owning release gate passes.

## Alternatives considered

- Feature chunks activating actions: rejected because AUTH would no longer be
  the sole authorization authority.
- Dual AUTH/feature activation ownership: rejected because parity and rollback
  would become ambiguous.
- A generic service locator or policy callback: rejected because resource facts,
  authority, and lifecycle ownership would become untyped.
- Mandatory contribution-evidence artifact generation: rejected for the core
  contribution transaction because canonical Review/Submission lineage already
  supplies its source facts.
- A combined submitter/reviewer role: rejected because unrelated capabilities
  must not replace or revoke one another.
- Adjudicator grant implying immediate adjudication capability: rejected until
  WS-REV owns the lifecycle and AUTH activates exact actions.

## Boundaries preserved

- No initiative imports another initiative's repositories or provider adapters.
- No feature service reads grants, assignments, or raw PermissionIds.
- No AUTH evaluator imports feature persistence or performs feature mutations.
- No provider I/O occurs while a business database transaction is open.
- Review packet/evidence semantics remain REV-owned; artifact bytes and bindings
  remain ART-owned.
- Contribution and compensation records remain CON-owned.

## Expected risks

- Existing plans may retain stale activation wording after this coordination PR.
- Current `ActionOwner` values may encode feature chunks and require atomic AUTH
  catalogue transfer before any affected action activates.
- Concurrent planning branches may be based on different trusted-main SHAs.
- Cross-domain lock order can deadlock if a downstream plan improvises locally.
- A service token may be provisioned but remain unusable if AUTH lacks a typed
  fixed-service admission path.

## What must not change

- No runtime code, migration, route, action availability, grant, service actor,
  provider profile, review decision, contribution record, or compensation
  behavior is changed by this planning initiative.
- Product review decisions remain `accept`, `needs_revision`, and `reject`.
- The existing ART-02A3 implementation remains independently reviewed and is
  not bundled into this planning PR.

## How this will be proven

- Complete action and service-identity matrices.
- Independent-role, role-specific invalidation, and service-admission handoff.
- Closed ownership and transaction tables for all four boundaries.
- Stale wording scans for feature-owned authorization activation.
- Internal architecture, security/auth, product/ops, senior, QA, docs, and reuse
  review before publication.

## Human decisions required

The user has selected AUTH-owned activation custody, separate parallel owner
work, no core CON-to-ART dependency, independent submitter/reviewer/adjudicator
grants, and a dedicated fixed-service runtime path. Each downstream initiative still needs
its own reviewed chunk contract and explicit start before implementation.
