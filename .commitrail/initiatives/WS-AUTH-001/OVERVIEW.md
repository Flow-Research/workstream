# WS-AUTH-001 — Workstream authorization service

Latest completed activation: [AUTH-12H complete-guide authority](WS-AUTH-001-12H.md),
following [AUTH-12G post-policy authority](WS-AUTH-001-12G.md).
Current remaining [plan](planning/PLAN.md) and [activation map](planning/CHUNK_MAP.md).

Historical pre-cutover work records: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Intent: provide deny-default, project-scoped authority with canonical human
  and service identities and attributable audit evidence.
- Current boundary: hidden projections and atomic setup finalization have exact
  request-local authority through AUTH-12J and AUTH-12B2; the five hidden
  ContributionPolicy actions have exact Finance Authority through CP05.
- Completed proposal boundary: AUTH-12F4 exact-project manager read, correction
  and pre-submit approval authority over hidden POL-05A behavior.
- Completed post-policy boundary: AUTH-12G fixed setup derivation and exact-project
  manager read, approval and correction authority over POL-06A.
- Public post-policy composition: POL-06B delivered using existing AUTH-12G.
- Completed activation boundary: AUTH-12H exact-project manager authority for
  CP07 complete-guide activation/binding, with live-authority replay.
- Next usable boundary: remaining ARCH-03B queues and actor-specific projections
  after completed ARCH-03B1 detached metadata and CP08 lineage
  and minimal writers and ARCH-03A internal guide context. POL-07B internal phase composition is delivered.
  Unavailable dispatcher contracts remain a separate contribution boundary.
- Governing source: `docs/spec_authorization_service.md`, authorization code,
  migrations, and tests.
- Preserve: Flow token verification only, no Workstream login/session system,
  exact action/permission catalogues, prepared mutation protocol, and
  fail-closed action availability.

## Delivered

- Flow-token verification, canonical actors/identity links, request and rate
  controls, audit/idempotency, project grants, bootstrap administration,
  fixed-service admission, controlled provisioning, and project read/mutation
  authorization are merged.
- Project-guide compilation request, recovery, fixed setup execution, and
  exact deterministic-projection authority are merged through `12J`; hidden
  POL projection ports exist through POL-04A3.
- AUTH-12B2 activates only fixed setup-service finalization of exact locked
  facts, with current lifecycle checks, immutable receipt binding, and exact
  historical replay. POL-04B composes its explicit adapter in the live Celery worker; default and
  public mutation ports remain unavailable.

## Remaining v0.1 sequence

Follow the [current cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract).
Hidden owner behavior precedes exact AUTH authority; neither guide activation
nor policy selection is authorized by the sufficiency action.

POL-06B exposes completed POL-06A operations with AUTH-12G authority.
POL-04B/05A/05B and AUTH-12F4 supply live unified setup and public
manager proposal review, pre-submit approval and manual correction dispatch.

1. CP07 complete-guide activation/binding and AUTH-12H live authority are delivered.
   ARCH-03A supplies complete internal guide facts before CP08 lineage and minimal writers.
2. ARCH-03B/03C replace broad AUTH-13 and ARCH-04D replaces AUTH-14/XINT-06B.
   AUTH-OUTBOX-01/02 bracket hidden CON-02B dispatch; ARCH-04E2 activates only
   the proven TASK routing handler before ARCH-04E3 live composition.
   Remaining cleanup/conformance and queue/read work must use its exact owner;
   do not execute those superseded broad designs.
