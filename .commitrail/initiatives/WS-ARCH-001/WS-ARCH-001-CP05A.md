# WS-ARCH-001-CP05A — Public ContributionPolicy administration

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: Finance Authority can discover, create, edit, publish,
  read and retire the existing project ContributionPolicy through the public API.

## Intent

Finish the public prerequisite for complete-guide activation. A manager must bind
an explicitly published policy; activation must not invent an unpaid default or
bypass Finance Authority. This is exposure of existing policy behavior, not award
materialization or fulfillment.

## Current behavior

Main `724459bc` includes ARCH-03C7. CP05 supplies the five live exact Finance
permissions; `contributions/service.py` and `policy_publication.py` own policy
commands, frozen versions, replay and validation. Their application adapters
compose PROJECTS eligibility and verified compensation bindings. There is no
public policy router. `scripts/api_contract_e2e.py::activate_guide_for_e2e`
still publishes a prerequisite internally. Public activation also lacks a manager
context containing discoverable approval/policy selections; that is the next
bounded change, not a reason to expose an unusable activation POST first.

## Bounded change

### Allowed

- `backend/app/api/routes/contribution_policies.py`, its request dependency and
  top-level API router: closed request bodies, typed responses and transactions.
- `backend/app/modules/contributions/api/`, `schemas.py`, `service.py`,
  `repository.py`, and the existing CON application adapter: a narrow typed
  operations port and project-current discovery through the existing read action.
- Existing AUTH adapter composition only; no new role, permission or action.
- Focused `backend/tests/contributions/` HTTP tests and signed Finance fixtures;
  existing contract, route/action inventory, semantic-lane and behavior-ownership
  registrations; API drill may exercise this policy workflow without claiming
  full public activation. Retain existing CON behavior and binding proof.
- README, canonical contribution specification, operating manual, roadmap and
  current ARCH navigation; this record; local sheet exports only if present.

### Not allowed

New policy semantics, default policy creation, Project Manager policy mutation,
new authorization powers, relaxed binding validation, award/payment/fulfillment
implementation, guide activation or Submission exposure, checker execution,
compatibility APIs, data deletion, new dependencies, weakened CI or coverage gates.
Do not touch the ongoing PR #444 test-audit implementation or tooling policy.

## Design and decisions

Use one API composition dependency with authenticated human context and the
existing exact Finance authorization adapter. End identity-read transactions
before entering the caller-owned policy transaction. Validate response facts
before commit so serialization failure rolls back mutation and authority evidence.

Expose project-scoped create-draft, exact version update/publish/retire and
exact policy/version read. Require one UUID Idempotency-Key on mutations; reject
missing, duplicate and malformed headers before actor resolution/product SQL,
without claiming precedence over token verification. Server context supplies
actor identity. Reuse the owner operation identifier as the replay selector;
never accept actor or authority facts in a body.

Add a bounded project-current discovery read under `contribution.policy.read`.
The owner first locates the single current non-retired policy, then authorizes
that exact policy through the existing read port before returning published and
open-draft version selectors. An independent Finance actor can recover these
selectors without the creator's receipt or idempotency key. Exact-ID reads keep
retired history available to authorized Finance callers. Absence/foreign/denial
remain concealed; no parallel policy list, cursor or permission system.

Support the already-defined complete unpaid graph (accepted_submission and
completed_review, no award definitions). Compensated graphs continue to require
valid verified bindings; binding administration remains separately internal.
Do not silently convert invalid compensated rules to unpaid rules.

## Acceptance criteria

1. Signed API flow creates, discovers, edits, publishes, reads and retires the
   existing policy with exact system/project Finance grants. Another Finance
   actor can discover a saved draft after the creator is revoked and finish it.
2. Project Manager, Operator, Contributor, foreign Finance, revoked actor/link/
   grant and service callers cannot access or mutate the resource. Exact project
   filters prevent foreign resource locks/data access; concealed errors persist.
3. Same-key same-command replay returns immutable original results after live
   reauthorization; altered command/project/actor or stale version cannot reuse
   it. Header errors reject before product composition; duplicate headers reject.
4. Public bodies cannot supply actor IDs, authority facts or storage fields.
   Both required contribution rules remain mandatory. Unpaid publication succeeds;
   malformed graphs and unsupported/foreign/unavailable compensated bindings fail
   using the existing validator, preserving state and evidence atomically.
5. Route validation/serialization/storage failures roll back actual staged
   lifecycle and authority rows; use independent-session verification. The API
   exposes existing behavior without replaying side effects or committing early.
6. Discovery returns only authorized current policy and draft/published selectors;
   exact historical reads remain available. OpenAPI and current documentation
   describe policy administration as public, activation/intake as still pending.

## Risk and review routing

- Risk class: L1, bounded Finance authorization/public policy exposure.
- Required reviewers: security/architecture/reuse; QA/test-delta/product-ops;
  documentation. CI integrity only if verification machinery changes materially.
- Human review focus: Finance versus manager powers, project scoping, recovery,
  unchanged explicit unpaid/compensated semantics and no premature activation.

## Evidence

Focused future signed PostgreSQL tests will cover the six criteria above using
existing real AUTH/CON composition. Run the existing owner validation/publication
proof where affected, route/schema and boundary checks, Ruff, Markdown links,
stale wording and Commitrail checks. Hosted canonical PostgreSQL/MinIO lanes and
coverage remain mandatory. No real inference or private guide input is needed.
Plan feasibility is inspected evidence, not runtime proof.

## Review findings

Initial feasibility review confirmed that public activation cannot precede a
usable public published-policy prerequisite. It also identified lost-selector
recovery; project-current discovery is included instead of requiring the next
Finance actor to possess the creator's original response.

## Reconciliation

- Current-source reconciliation: CP05/CP06/CP07/AUTH-12H and ARCH-03C7 are
  delivered; public policy administration and activation remain absent.
- Next usable boundary: manager activation context and public activation using
  CP07/AUTH-12H, then approved-guide intake integration. The API drill's internal
  activation helper is removed when its complete public replacement lands.
- Remaining risks: compensated policy creation still needs an existing verified
  binding; public binding administration and fulfillment are not claimed here.
