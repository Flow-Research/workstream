# WS-AUTH-001 — Workstream authorization service

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Intent: provide deny-default, project-scoped authority with canonical human
  and service identities and attributable audit evidence.
- Current boundary: hidden POL-04A3 projections and their exact request-local
  AUTH-12J authority are complete.
- Next usable boundary: implement 12B2 after POL-04A2 finalization; 12B2 owns
  concrete current-service revocation and production receipt-integrity proof.
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

## Remaining v0.1 sequence

1. POL-04A2 then `12B2`: hidden setup finalization followed by its exact
   authority. The concrete adapter's revocation and receipt-integrity proof
   belongs to 12B2, not to hidden POL-04A2.
2. `12F4`, `12G`, and `12H`: activate stored pre-submit/post-submit and final
   guide behavior only after their owner implementations and CON CP05-CP07.
3. Reframe `13`-`16` against then-current TASK, checker, cleanup, and
   conformance behavior; do not execute the obsolete broad `14` design.
