# Chunk Contract: WS-POL-003-07 - Single Checker Service Port

Disposition: Complete. Dependencies: 06B, ARCH-04A capability contracts,
merged ART-04B1-04B3, and [POL-07A ART attempt custody](../../WS-POL-003-07A.md). Risk: L1.

The plan review identified that ART's evidence deduplication originally happened
only after execution. POL-07A supplies the committed reservation and canonical
recovery prerequisite; this facade chunk consumes that owner capability. Its
ART lifecycle exclusion applies after that separately bounded repair.

## Current bounded contract

[POL-07B](../../WS-POL-003-07B.md) is the reviewed implementation contract
for this boundary after the completed POL-07A attempt prerequisite. It replaces
the earlier overbroad execution claims in this planning chunk.

- Compose exactly two internal phase commands without a second compiler,
  executor, evidence writer or authorization path.
- After ART reservation commits, call `evaluate_pre_submission` once for both
  a winning reservation and completed replay. Pass the same opaque selection to
  the same ART evidence owner, with the consumed prepared authorization cleared.
  Do not open a transaction at this handoff. ART's existing operation obtains
  fresh authority, executes the locked plan when warranted, and returns its
  canonical evidence unchanged. Replay invokes no members or new upload capability.
- `evaluate_post_submission` validates and delegates CHECKERS' closed value
  contract. ARCH-04C supplies the hidden durable executor and currentness;
  ARCH-04D2 supplies exact input, execute and finalize service authority.
  The facade's request/result correspondence remains value-consistency proof;
  those owner operations enforce authorization and durable execution custody.
- ARCH-04B supplies verified input and ARCH-04B2 supplies hidden output custody.
  Output write/bind authority remains unavailable for the zero-output catalogue.
  ARCH-04E event invocation/routing remains separate. Its event handler invokes
  the facade; the injected executor must not call the facade recursively.
- Remove the standalone draft JSON precheck, its exclusive code, schemas and
  tests together. Preserve shared helpers used by current post-submit consumers.
  Broader public Submission cutover remains WS-ARCH-001-02I.
- Consume ARCH-04A registered implementation/configuration contracts without
  changing guide activation. CP07/AUTH-12H own activation; it must not require a
  Task, Submission, completed CheckerRun or live post-submit execution.

## Scope and proof

The [bounded change record](../../WS-POL-003-07B.md) enumerates allowed files,
prohibitions, counterexample/control tests, review tracks and human focus.
No ART scratch, storage, claim, lock order or persistence changes are permitted.
No production post executor, new route, per-checker dispatch or compatibility
path is introduced. Test completed pre replay through the facade, real ART
reservation/claim and authority custody, result identity, post contract denial,
and complete JSON-precheck removal. Keep changed subsystem coverage at least 90%.
