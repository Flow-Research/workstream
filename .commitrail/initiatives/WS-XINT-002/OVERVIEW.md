# WS-XINT-002 — ART/AUTH end-to-end integration

Current pre-review work follows the [cross-owner dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
and the [capability ledger](../../../docs/roadmap_status.md).

- Disposition: Planned
- Completed boundary: guide and pre-submit materialization activation.
- Intent: connect AUTH-owned admission with ART-owned immutable artifact
  behavior without transferring resource ownership.
- Next usable boundary: only remaining activation edges required by the
  artifact delivery path.
- Governing sources: artifact and authorization specifications, code,
  migrations, and crossed-boundary tests.
- Preserve: AUTH owns authority; ART owns artifact facts and mutations; exact
  hidden behavior precedes availability.

For remaining work, the [current dependency contract](../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
assigns post-submit activation solely to ARCH-04D2 and checker-remediation
resubmission to ARCH-04F. XINT-06B/05C are historical predecessor designs, not
additional PRs. Later reviewer/revision integration is outside this reconciliation.

## Preserved history

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).
These verbatim records preserve completed work and original proposals; where
pending sequencing conflicts, the current dependency contract above governs.
