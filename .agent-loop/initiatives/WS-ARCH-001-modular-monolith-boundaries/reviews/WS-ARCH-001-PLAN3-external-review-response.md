# WS-ARCH-001 PLAN3 External Review Response

## Comments addressed

- Added explicit STATUS projection for CP01 through CP09 so atomic chunk-state
  validation can reconcile every CHUNK_MAP identifier.
- Removed the AUTH-12H cycle. AUTH-12H depends on POL-07, CP05 active policy
  behavior, CP06 validation, and CP07 ProjectGuide binding only. CP08,
  WS-ARCH-001-03A/03B/03C, and CP09 are downstream.
- Qualified every ambiguous PLAN3 `03C activation` reference as
  `WS-ARCH-001-03C` where CON also owns a distinct 03C.
- CP01 remains a planning skeleton only. Its pre-start contract must split the
  two registration families or prove one bounded unavailable-only shared
  catalogue/context change with independent parity tests.
- Aligned the canonical CP07 -> CP08 -> WS-ARCH-001-03A dependency in the
  initiative map and made AUTH's projection defer to that owner sequence.
- Named all four immutable policy-lineage fields in the CON conformance proof
  and restored the complete CP01-CP08 -> ARCH-03A/03B/03C release chain.
- Recorded the replacement activation and CP09 clean-removal gate in the
  capability ledger.
- Distinguished the covered Project Manager HTTP entry from the fixed project
  setup service's internal command resolution in CP07.
- Corrected the still-proposed AUTH-12H contract so guide activation depends on
  POL-07, corrected 12B2, CP05, CP06, and CP07 only. Its retired economic
  fields confer no authority; CP08, ARCH-03A/03B/03C, and CP09 remain
  downstream, removing the last active documented cycle.

## Comments deferred

- CodeRabbit comments against historical CON 04A/04B/05A/05B/08A bodies were
  not applied. Those merged chunk contracts are immutable historical evidence;
  active CHUNK_MAP/STATUS/runtime records already mark them non-executable and
  point to the current CP replacements. Editing their landed contract bodies
  would violate the repository's atomic chunk-state history gate.
- The suggested edit to `WS-AUTH-001-12-project-mutation-cutover.md` was
  reverted after exact-head Agent Gates correctly identified it as the rejected,
  non-executable planning parent with immutable landed outcome. D38, the active
  AUTH map/status, PLAN3, and the corrected 12H contract supersede its original
  future sequence; the parent is historical evidence, not implementation
  authority.

## Human decisions needed

None beyond normal approval of the corrected planning PR.

## Commands rerun

```text
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_chunk_state_sync.py --base-ref 020763ab5b8a81c9ef37fe9e7ef23f68a281f290
git diff --check
```

## Remaining risks

CP01 boundedness is intentionally a mandatory pre-start decision. No runtime
implementation is authorized by PLAN3.
