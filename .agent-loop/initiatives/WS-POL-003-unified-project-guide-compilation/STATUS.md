# Status: WS-POL-003 - Unified Project Guide Compilation

Planning reconciliation merged through PR #298. `WS-POL-003-01` merged through
PR #299 and established the strict unified contract catalogue.
`WS-POL-003-02` merged through PR #301 and added the single unified guide agent
adapter with fake-runtime proof. Open pull requests, not this static file,
determine transient implementation ownership.

## Current delivery truth

- One logical model attempt per immutable guide/catalogue/setup generation is
  the sole target design.
- The complete accepted result contains sufficiency, artifact, pre-submit, and
  post-submit proposals before any approval.
- AUTH-12E and AUTH-12F3 are merged transitional separate-call
  implementations. Their action-specific projection custody is reusable; their
  independent inference paths must not survive POL-04B.
- ART-04B1, 04B2, 04B3, XINT-06A, and ART-04C1 are merged. ART admission may
  continue independently through its dependency sequence.
- Remaining AUTH-12F4, 12G, 12B2, and 12H contracts require reconciliation as
  narrow activation gates around hidden POL behavior. They are not authority
  for another inference pipeline.

## Dependency gates

| Dependency | Required before | Current status |
|---|---|---|
| ART-04B1 complete pre-submit catalogue/effective plan | POL-01 | Merged PR #276 |
| Canonical CHECKER/POL post-submit registry | POL-01 | Present; remaining POL-002 work must be reframed as executor ownership, not inference |
| POL-01 strict manifest | POL-02 | Merged PR #299 |
| POL-02 adapter | POL-03A | Merged PR #301 |
| Hidden POL-03A compilation custody | AUTH-12I compilation request/execute activation | POL-03A merged PR #307; AUTH-12I not implemented |
| AUTH-12I | POL-03B authorized persistence | Not yet implemented |
| Hidden POL-04A unified setup-service manifest | AUTH-12B2 setup-ledger activation | Not yet implemented |
| Hidden POL-05A approval manifest | AUTH-12F4 approval activation | Not yet implemented |
| Hidden POL-06A deterministic post manifest | AUTH-12G projection/approval activation | Not yet implemented |
| Complete POL-07 single checker port + corrected 12B2 + CON clean cut | AUTH-12H | Not yet implemented |
| ART-05B + POL-07 + ART-06A/06B evidence | XINT-06B and AUTH-14 | Not yet implemented |

## Chunk state

POL-01 and POL-02 are merged. The newly split
03A-06B and corresponding AUTH gates are reviewed planning skeletons only:
before any is started, its contract must be expanded on then-current main with
explicit allowed/not-allowed paths, runnable verification commands, and named
reviewer tracks. They cannot authorize implementation in their current form.

`WS-POL-003-03A` merged through PR #307 at `5e459a8f`. It installs hidden
compilation custody and the first public AUTH-capability consumer proof without
activating request/execute authority. AUTH-12I is the next dependency gate;
later chunks and AUTH gates remain planned and inactive.
