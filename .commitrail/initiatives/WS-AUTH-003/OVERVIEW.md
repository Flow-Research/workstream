# WS-AUTH-003 — Authorization module-boundary recovery

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Delivered prerequisite: [ART-07A1](../WS-ART-001/WS-ART-001-07A1.md) supplies
  metadata-only packet types. REV-03B packets and REV-04A immutable Review source storage are delivered; REV-04B shared FinalAcceptance storage is delivered; CON-03C contribution/award storage and REV-12A1 disabled controller/fence are delivered; mandatory acceptance-source AUTH custody precedes atomic participation. No packet resolver or human runtime is live.

- Completed boundary: recovery foundation and [TASK/checker authorization cleanup](WS-AUTH-003-TASKCHECKER.md).
- Intent: route public authorization capability through `authorization.api`
  and remove cross-module repository/model coupling.
- Delivered dependent boundary: ARCH-04E1A route-neutral source facts and
  source-neutral accepted-effects types follow ARCH-04D2 exact service authority,
  ARCH-04C hidden execution, ARCH-04B hidden input,
  [ARCH-04B2 output custody](../WS-ARCH-001/WS-ARCH-001-04B2.md), ARCH-03D hidden
  intake and [AUTH-18 public manager activation](../WS-AUTH-001/WS-AUTH-001-18.md).
  ARCH-04E2-A then adds strict AUTH-private resource/preparation matching and a
  nominal fixed-router adapter through canonical PREP. The action remains
  planned/unavailable; it installs no handler, source writer or runtime composition.
- Delivered storage: [REV-03B](../WS-REV-001/WS-REV-001-03B.md) freezes exact
  lease packets with normalized live guide ingests; no resolver or byte authority.
  [REV-04A](../WS-REV-001/WS-REV-001-04A.md) adds complete immutable Review, findings, resolutions and completed request storage; no decision runtime.
- Next usable boundary: for the selected automated-acceptance delivery sequence, continue canonical boundary recovery through CON-07/shared acceptance
  foundations and later ARCH-04E1B-B/04E2-B/04E3 routing.
  Submission/checker history uses canonical authority; the alternate gate lifecycle
  is removed. Continue shrinking the canonical import ledger as implementation
  reaches each remaining consumer.
- Governing sources: `docs/architecture_lockdown.md`,
  `.ci/auth-boundaries/IMPORT_LEDGER.md`, module-boundary scripts, and tests.
- Preserve: the ledger is CI debt data, not engineering authority, and may only
  shrink unless a separately reviewed architecture change authorizes growth.

This is delivery priority, not a prerequisite of true human admission. Both
routing branches have delivered request reservation 04E1B-A and exact AUTH preparation 04E2-A before hidden 04E1B-B → activation 04E2-B → live 04E3; true routing
can proceed after its own prerequisites without CON-07/shared acceptance or
scoped lifecycle activation. False routing adds those requirements. Human final
acceptance later uses the same authorized shared acceptance/CON operation.
