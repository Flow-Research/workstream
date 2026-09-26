# WS-AUTH-003 — Authorization module-boundary recovery

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: recovery foundation.
- Intent: route public authorization capability through `authorization.api`
  and remove cross-module repository/model coupling.
- Next usable boundary: [TASK/checker authorization cleanup](WS-AUTH-003-TASKCHECKER.md),
  replacing retained-history authority and removing the alternate gate lifecycle
  before resuming public guide integration. Shrink the canonical import ledger
  as affected consumers are replaced.
- Governing sources: `docs/architecture_lockdown.md`,
  `.ci/auth-boundaries/IMPORT_LEDGER.md`, module-boundary scripts, and tests.
- Preserve: the ledger is CI debt data, not engineering authority, and may only
  shrink unless a separately reviewed architecture change authorizes growth.
