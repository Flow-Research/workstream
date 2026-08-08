# Status: WS-POL-003 - Unified Project Guide Compilation

Status: planning reconciliation active; no implementation chunk is active.

Baseline: `origin/main` `99c0aaf04efd36c7ac4af4aeec2e9d810f012305`
after merged AUTH-12F3 PR #295.

## Current delivery truth

- One logical model attempt per immutable guide/catalogue/setup generation is
  the sole target design.
- The complete accepted result contains sufficiency, artifact, pre-submit, and
  post-submit proposals before any approval.
- AUTH-12E and AUTH-12F3 are merged transitional separate-call
  implementations. Their action-specific projection custody is reusable; their
  independent inference paths must not survive POL-04B.
- ART-04B1, 04B2, 04B3, and XINT-06A are merged. ART-04C1 is ready to proceed
  independently through the admission sequence.
- Remaining AUTH-12F4, 12G, 12B2, and 12H contracts require reconciliation as
  narrow activation gates around hidden POL behavior. They are not authority
  for another inference pipeline.

## Dependency gates

| Dependency | Required before | Current status |
|---|---|---|
| ART-04B1 complete pre-submit catalogue/effective plan | POL-01 | Merged PR #276 |
| Canonical CHECKER/POL post-submit registry | POL-01 | Present; remaining POL-002 work must be reframed as executor ownership, not inference |
| POL-01/02 strict manifest and adapter | POL-03A | Proposed |
| Hidden POL-03A compilation manifest | AUTH-12I compilation request/execute activation | Proposed |
| AUTH-12I | POL-03B authorized persistence | Not yet implemented |
| Hidden POL-04A unified worker manifest | AUTH-12B2 setup-ledger activation | Not yet implemented |
| Hidden POL-05A approval manifest | AUTH-12F4 approval activation | Not yet implemented |
| Hidden POL-06A deterministic post manifest | AUTH-12G projection/approval activation | Not yet implemented |
| Complete POL-07 single checker port + corrected 12B2 + CON clean cut | AUTH-12H | Not yet implemented |
| ART-05B + POL-07 + ART-06A/06B evidence | XINT-06B and AUTH-14 | Not yet implemented |

## Chunk state

POL-01 and POL-02 retain their full executable contracts. The newly split
03A-06B and corresponding AUTH gates are reviewed planning skeletons only:
before any is started, its contract must be expanded on then-current main with
explicit allowed/not-allowed paths, runnable verification commands, and named
reviewer tracks. They cannot authorize implementation in their current form.

All WS-POL-003 chunks and corresponding AUTH gates are proposed and inactive.
The current work is planning-only. The first executable candidate after this
planning PR merges is `WS-POL-003-01`, subject to a separate explicit start and
fresh preimplementation review.
