# Internal Review Evidence: WS-ENG-008-01

## Chunk

`WS-ENG-008-01` — Machine-Checkable Chunk Scope

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Signed Start Provenance

- Authorized main SHA: `bd2203d5e8a972d8afbf833805b92ed70dedee4a`
- Signed start run: `30191914510`
- Signed state commit: `6923f9ed4a8e48327d3aa4d046c8a8dc3a31ea3`
- Contract path: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-01-machine-checkable-chunk-scope.md`
- Signed contract blob: `2fb0afba71653e7aefcc074079fe98f44051c068`

## Reviewed Revision

Reviewed code SHA: `1ef5c3bd0bffedec684ae8b6cec2e6affbcb3b21`

Reviewed at: `2026-07-26T07:48:30Z`

Reviewer run IDs: `ci02b_lane_runner`, `ci02b_cr_arch`, `ci02b_cr_ci`, `ci02b_cr_docs`, `ci02b_cr_reuse`, `ci02b_cr_test_delta`

After the reviewed SHA, only initiative evidence, trust-bundle, external-review,
and status files may change.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Exact final SHA; dead scope-free grandfather path removed. |
| QA/test | PASS | None | Twenty-seven focused tests cover the required real-Git mutation classes. |
| security/auth | PASS | None | Signed ledger, exact blob, grandfather, path, and trusted-base boundaries verified. |
| product/ops | PASS | None | Repository process remains separate from product lifecycle and authority. |
| architecture | PASS WITH LOW RISKS | None | Trusted-base execution closes candidate self-authorization; explicit dependency custody is acceptable. |
| CI integrity | PASS | None | No workflow, test, coverage, package, or permission weakening. |
| docs | PASS | None | Entry docs, glossary, lockdown, policies, and templates agree. |
| reuse/dedup | PASS WITH LOW RISKS | None | Local ledger/intent/reviewer parsing creates bounded future consolidation opportunities. |
| test delta | PASS | None | No tests removed or skipped; direct runner includes new regressions. |

## Valid Findings Addressed

- Candidate-code self-authorization: post-cutover Agent Gates materialize the
  checker and both signed-state validators from the trusted PR base. The only
  head-code bootstrap is bounded to a base containing neither the checker nor
  the `WS-ENG-008-01` cutover marker.
- Grandfather scope bypass: eligibility and scope now derive from authenticated
  ledger events plus the exact signed legacy contract blob; all grandfathered
  changes pass normal scope enforcement.
- Untracked and alias bypasses: no-follow regular-file checks reject untracked
  symlinks/executables, while full resulting-tree validation rejects byte, NFC,
  and casefold collisions.
- Git mutation gaps: real repositories cover staged, dirty, untracked, rename,
  copy, executable, symlink, gitlink, type-change, invalid UTF-8, non-NFC,
  cancel, stop, restart, and post-cutover schema failures.
- Template/evidence drift: the chunk template includes Start phase, and machine
  verification IDs bind the existing Commands Run fence to closed
  repository-owned command strings.

## Commands Run

```bash
python3 scripts/test_check_chunk_contract.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Results

- Machine scope tests: 27 passed.
- Agent Gate regressions: 102 passed.
- Exact signed-state scope selection: passed.
- Schema-v2 merge intent: passed.
- Ruff, Markdown links, stale wording, and diff checks: passed.

## Remaining Risks

- Reviewer names, merge-intent identity parsing, and the authenticated ledger
  reduction have small duplicate representations across existing gate modules.
  Reviewers classified consolidation as Low risk; it must not be performed in
  this security-boundary chunk without a separate contract.

