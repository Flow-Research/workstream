# External Review Response: WS-CON-001-PLAN4

## Comments addressed

CodeRabbit raised four initial findings and two refreshed-review findings on
PR #261:

1. Receipt quantities/units and digest provenance were under-specified. The
   `03D` contract now permits only the canonical award quantity/binding unit and
   platform-generated digests derived exclusively from approved receipt fields,
   with explicit negative tests for forbidden digest inputs.
2. The authorization conformance row allowed a runtime-inspection exception.
   It now records current CON AUTH artifacts as absent and requires exact
   AUTH-owned registration and activation evidence for every future artifact.
3. The provider-receipt risk mitigation used an incomplete exclusion list. It
   now denies provider bodies, secrets, tokens, signatures, URLs, PII, balances,
   ledgers, settlement data, and digests derived from forbidden inputs.
4. Dependency summaries omitted `04A -> 04B`, `03B -> 03C`, and `04A/04B ->
   08A` gates. The canonical specification, chunk map, and executable `04B`,
   `03C`, and `08A` child contracts now include them.
5. The `08A` child contract omitted its explicit `03D` receipt-persistence
   prerequisite. Its executable prerequisite gate now includes `CON-03D`.
6. Two canonical dependency views used broad REV persistence labels. Both now
   require the exact merged `REV-04B` runtime `Review`, `ReviewLease`, and
   `FinalAcceptance` targets required by the `03C` child contract.

Internal repair review then found the canonical receipt section still allowed
ambiguous request/payload digests. The specification now matches `03D`: only
platform-generated digests over approved stored receipt fields are allowed,
and digests over any forbidden provider/sensitive input are rejected.

The PR description warning is also addressed by publishing the complete trust-
bundle sections in the PR body.

## Comments deferred

None.

## Hosted CI triage

Backend run `30848526550` failed only
`tests/test_auth.py::test_actor_profile_lifecycle_real_postgres_concurrency`
in `shared_foundations` after 2,210 tests passed. The same AUTH concurrency test
failed on current main run `30871111339`. PLAN4 changes no AUTH runtime, tests,
workflow, or CI configuration. The branch was refreshed through current main;
publication still requires a green rerun or an AUTH-owned upstream repair.

## Human decisions needed

No new decision. Human review and merge ownership remain unchanged.

## Commands rerun

- `git diff --check`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 -m unittest -v scripts.test_lightweight_agent_gates`

## Remaining risks

ART #249 is merged. Migration allocation and all future AUTH, REV, provider,
callback, and legacy-row gates must be refreshed at their owning chunk.
