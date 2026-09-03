# WS-XINT-002 — ART/AUTH end-to-end integration

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

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
