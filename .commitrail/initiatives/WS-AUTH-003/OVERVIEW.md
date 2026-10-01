# WS-AUTH-003 — Authorization module-boundary recovery

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: recovery foundation and [TASK/checker authorization cleanup](WS-AUTH-003-TASKCHECKER.md).
- Intent: route public authorization capability through `authorization.api`
  and remove cross-module repository/model coupling.
- Next usable boundary: ARCH-04E1A routing-source facts after delivered ARCH-04D2 exact service authority, ARCH-04C hidden execution and ARCH-04B
  hidden input, [ARCH-04B2 output custody](../WS-ARCH-001/WS-ARCH-001-04B2.md), ARCH-03D hidden intake and
  [AUTH-18 public manager activation](../WS-AUTH-001/WS-AUTH-001-18.md).
  Submission/checker history uses canonical authority; the alternate gate lifecycle
  is removed. Continue shrinking the canonical import ledger as implementation
  reaches each remaining consumer.
- Governing sources: `docs/architecture_lockdown.md`,
  `.ci/auth-boundaries/IMPORT_LEDGER.md`, module-boundary scripts, and tests.
- Preserve: the ledger is CI debt data, not engineering authority, and may only
  shrink unless a separately reviewed architecture change authorizes growth.
