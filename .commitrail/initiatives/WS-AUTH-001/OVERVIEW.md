# WS-AUTH-001 — Workstream authorization service

Latest completed activation: [AUTH-12F4 proposal authority](WS-AUTH-001-12F4.md), following [CP05 ContributionPolicy authority](../WS-ARCH-001/WS-ARCH-001-CP05.md).
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
- Next usable boundary: POL-05B manager-facing composition.
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

1. POL-04B delivers live automatic compilation and exact AUTH-12B2 finalization.
   POL-05A adds hidden manager review, correction and pre-submit approval.
   AUTH-12F4 supplies its authority; next POL-05B supplies public composition and manual dispatch.
2. `12G` and `12H`: activate stored pre-submit/post-submit and final
   guide behavior only after their owner implementations and remaining CON CP06-CP07.
3. ARCH-03B/03C replace broad AUTH-13 and ARCH-04D replaces AUTH-14/XINT-06B.
   AUTH-OUTBOX-01/02 bracket hidden CON-02B dispatch; ARCH-04E2 activates only
   the proven TASK routing handler before ARCH-04E3 live composition.
   Remaining cleanup/conformance and queue/read work must use its exact owner;
   do not execute those superseded broad designs.
