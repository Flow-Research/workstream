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
| Hidden POL-03A compilation custody | AUTH-12I compilation request/execute activation | POL-03A merged PR #307; AUTH-12I merged PR #312 |
| AUTH-12I | POL-03B authorized persistence | Merged PR #312; dependency satisfied |
| Hidden POL-04A unified setup-service manifest | AUTH-12B2 setup-ledger activation | `WS-POL-003-04A` complete on its stacked branch; human merge required |
| Hidden POL-05A approval manifest | AUTH-12F4 approval activation | Not yet implemented |
| Hidden POL-06A deterministic post manifest | AUTH-12G projection/approval activation | Not yet implemented |
| Complete POL-07 single checker port + corrected 12B2 + CON clean cut | AUTH-12H | Not yet implemented |
| Canonical WS-ARCH-001-04E manifest + POL-07 | POL-08 cleanup and later AUTH/REV admission | Not yet implemented; historical ART-05A/05B are non-executable |

## Chunk state

POL-01 and POL-02 are merged. The newly split
03A-06B and corresponding AUTH gates are reviewed planning skeletons only:
before any is started, its contract must be expanded on then-current main with
explicit allowed/not-allowed paths, runnable verification commands, and named
reviewer tracks. They cannot authorize implementation in their current form.

`WS-POL-003-03A` merged through PR #307 at `5e459a8f`, and AUTH-12I merged
through PR #312 at `98eae13e`. `WS-POL-003-03B` is complete. It installs the
hidden internal coordinator, migration 0008 request custody, SQL digest and
authorization trigger, explicit dispatch-versus-recovery receipts,
current-setup lineage checks, real-PostgreSQL concurrency and crash proof, and
semantic-lane registration. `WS-POL-003-04A` is complete on its stacked
branch. It adds one execution-only hidden command over an already authorized
attempt, preserves unresolved provider outcomes without redispatch, and leaves
all live routing and setup projections untouched. AUTH-12B2 and POL-04B are
the next boundaries. The stacked work remains transient until a human merges
its parent and this branch; protected main does not yet have this behavior.

WS-POL-003-08 is planned only after the canonical WS-ARCH-001-04E manifest and
is not a prerequisite for WS-ARCH-001-03A.
