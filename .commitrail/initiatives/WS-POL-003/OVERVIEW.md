# WS-POL-003 — Unified project-guide compilation

Current change record: [POL-04A2 hidden finalization](WS-POL-003-04A2.md).

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: hidden execution and deterministic projections.
- Intent: compile one locked guide and its policies into authoritative,
  versioned project behavior without circular subsystem authority.
- Next usable boundary: implement the reviewed 04A2 hidden finalization
  contract, then its exact AUTH gate before 04B live cutover.
- Governing sources: project-guide specifications, authorization and
  contribution-policy specifications, code, migrations, and tests.
- Preserve: deterministic compilation, explicit ownership, atomic persistence,
  no hidden activation, and no concrete adapter leakage.

## Delivered

- Strict unified catalogue, one guide-agent adapter, authorized immutable
  compilation persistence/recovery, hidden execution, and deterministic
  sufficiency/artifact-policy projections are merged through 04A3.

## Remaining v0.1 sequence

1. Implement the planned POL-04A2 hidden setup-ledger finalization contract;
   AUTH-12J projection authority is already complete.
2. AUTH-12B2 exact finalization authority, then POL-04B live explicit-manager
   cutover with every legacy inference call removed from reachability.
3. POL-05/06 approval and post-submit manifests with AUTH-12F4/12G.
4. POL-07 canonical checker port, AUTH-12H, and later POL-08 cleanup after the
   canonical ARCH-04E manifest.
