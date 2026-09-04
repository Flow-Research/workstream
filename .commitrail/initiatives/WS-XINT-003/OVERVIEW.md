# WS-XINT-003 — REV/AUTH end-to-end integration

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: review authorization readiness through 02D.
- Intent: bind AUTH authority to REV-owned facts and lifecycle guards without
  local role logic or circular repository access.
- Next usable boundary: later activation waves resume only against exact merged
  REV behavior.
- Governing sources: `docs/spec_authorization_service.md`,
  `docs/spec_review_lifecycle.md`,
  `docs/engineering/review_authorization_action_custody.md`, code, and tests.
- Preserve: unavailable-by-default actions, exact service principals, fresh
  authority inside transactions, and feature-owned row locks/final facts.
