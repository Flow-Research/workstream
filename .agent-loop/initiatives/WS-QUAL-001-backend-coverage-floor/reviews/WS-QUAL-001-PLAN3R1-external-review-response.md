# WS-QUAL-001-PLAN3R1 External Review Response

## Comments addressed

- PR #272 discussion `3714978005`: PR-editable dependency manifests are no
  longer trusted as mutation-tool authority; the contract requires authority
  from a protected base revision or an equivalent protected runtime that
  already exists before 04M and cannot be introduced or modified by 04M.
- PR #272 discussion `3714978015`: test-only behavior claims are additive and
  cannot replace mutation of eligible changed production targets.
- PR #272 discussion `3714978020`: every engine status must block or map to an
  independently verified typed classification; implicit passing is forbidden.
- PR #272 discussion `3714978023`: fixture-only changes are exempt only after
  evidence proves they cannot influence selection, inputs, or assertions.
- PR #272 discussion `3714978026`: PLAN3 Backend evidence now binds run
  `30926337804` to commit `5f2baf90`.

## PR #278 follow-up comments addressed

- Standardized the canonical mutation status label as `error` across PLAN,
  04M evidence, INTENT, DISCOVERY, and the 05M gateway.
- Separated the PLAN3R1 stop, explicit 04M start, 04M calibration checkpoint,
  and explicit evidence-bound 05M start.
- Clarified that dependency authority comes from a protected base revision.
- Corrected the trust-bundle scope evidence to twelve changed paths.

## Comments deferred

None.

## Human decisions needed

None. This chunk corrects merged planning and does not implement mutation CI.

## Commands rerun

- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py`
- `git diff --check`

## Remaining risks

The mutation engine and exact executable policy remain intentionally undecided
until separately authorized `WS-QUAL-001-04M` implementation and hosted pilot
evidence.
