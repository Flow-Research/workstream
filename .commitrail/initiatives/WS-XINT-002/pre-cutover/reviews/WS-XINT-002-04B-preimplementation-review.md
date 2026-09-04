# Preimplementation Review: WS-XINT-002-04B

## Initial result

Security, architecture, and QA returned `FAIL` against the original contract.
The direction was correct, but the contract did not enumerate the exact guide
binding/read resource facts, explicitly require closed AUTH resource contexts,
include the guide-binding behavior tests, or distinguish AUTH adapter delivery
from ART-03C live composition.

## Corrections

- Replaced the obsolete aggregate ART predecessor with the complete split-03B
  merge list.
- Enumerated every binding and read resource fact from the merged ART handoff.
- Required two closed typed AUTH resource contexts and exact PREP/kernel
  consume-time binding without broadening generic ART-internal selectors.
- Added copied, replayed, cross-session, cross-action, cross-service,
  cross-resource, stale-lineage, and field-level mismatch denial proof before
  provider I/O or protected mutation.
- Required handles to remain process-local and absent from Celery and all
  serialization surfaces.
- Added `backend/tests/test_guide_bindings.py` to allowed scope and verification.
- Assigned production AUTH adapter delivery to 04B while retaining Celery task,
  route, orchestration, and legacy cutover ownership in ART-03C.
- Required the obsolete `WS-AUTH-001-ART-03` owner label to be replaced by
  `WS-XINT-002-04B` without aliases or duplicate action paths.

## Final result

- Security: `PASS`; no remaining blockers.
- QA/test: `PASS`; no missing blocking criteria.
- Architecture: `PASS WITH LOW RISKS`; no boundary or composition blocker.
  The only wording observation about current versus future owner state was
  clarified in discovery.

The corrected contract is ready for human review. Runtime implementation must
not begin until this planning amendment merges.
