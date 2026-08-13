# WS-ARCH-001 PLAN2 Internal Review

Scope: planning-only reconciliation from current merged admission-backed
Submission foundations to one canonical durable `allow_review` milestone.

## Findings resolved

- Removed the circular POL-08 prerequisite; unified guide readiness ends at
  AUTH-12H before WS-ARCH-001-03 begins, while physical POL-08 cleanup follows
  canonical 04E.
- Marked retired ART-05/06, XINT-06B and AUTH-14 paths superseded and
  non-executable so there is one post-submit path.
- Made 04C hidden and deny-only until exact AUTH activation in 04D.
- Required reuse of existing PROJECT, TASK and the single POL checker public
  contracts rather than parallel APIs.
- Expanded canonical 04E eligibility and denial facts and separated
  contributor checker remediation into 04F before public cutover.
- Marked 03A-04F as non-executable planning skeletons that require exact
  current-main contracts before implementation.

## Reviewer result

Architecture, authorization security, product/operations, senior engineering,
documentation and reuse reviews were required. Every valid finding was
applied and each track returned a final pass before this planning change was
reported ready.

## Verification

- `git diff --check`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 -m pytest -q scripts/test_lightweight_agent_gates.py`
