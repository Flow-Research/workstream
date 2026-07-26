# Internal Review Evidence

## Chunk

`WS-ENG-008-PLAN` — Repository-Native SDLC Assurance Planning

This planning review covers the initiative artifacts and reviewed contracts
`WS-ENG-008-01` through `WS-ENG-008-07`. It authorizes no implementation and
leaves both active slots empty.

## Required Statements

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 8ce2c1cffd63ba9a8a4867773fe38d7861d2fa69

Reviewed at: 2026-07-26T01:29:34Z

Reviewer run IDs: senior-engineering=`ci02b_lane_runner`;
QA/test=`ci02b_cr_arch`; security/auth=`ci02b_cr_ci`;
product/ops=`ci02b_cr_docs`; architecture=`ci02b_cr_arch`;
CI-integrity=`ci02b_cr_ci`; docs=`ci02b_cr_docs`;
reuse/dedup=`ci02b_cr_reuse`; test-delta=`ci02b_cr_test_delta`.

After the reviewed SHA, only this evidence and trust bundle changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Signed-active-only grandfathering, successor conversion, sequencing, semantic lanes, and budgets are bounded. |
| QA/test | PASS | None | Exact start ratchet, negative path cases, measurable limits, and acceptance criteria pass. |
| security/auth | PASS | None | Event/blob binding, path-byte controls, read-only audit, and AUTH reconciliation are explicit. |
| product/ops | PASS | None | Engineering assurance remains separate from product review and Contributor authority. |
| architecture | PASS | None | ENG-008 cannot exempt successors or post-cutover starts; canonical authority paths remain. |
| CI integrity | PASS | None | Planning changes no CI surface; future locks and budgets preserve blocking gates. |
| docs | PASS | None | Historical discovery and current reconciliation are distinct and consistent. |
| reuse/dedup | PASS | None | Existing validators, evidence gate, risk router, reviewers, aggregation, and initiative reviews are reused. |
| test delta | PASS | None | Planning-only diff changes no test, workflow, threshold, or application file. |

## Valid Findings Addressed

- Replaced subjective “materially changed” scope with an exact start cutover:
  every post-cutover implementation/specification start requires schema; only
  chunks already signed-active at cutover are grandfathered, bound to their
  exact start event and contract blob.
- Required chunk 01 to convert and validate ENG-008 contracts 02–07 before it
  may name chunk 02, closing the initiative's self-exemption gap.
- Required byte-preserving NUL-delimited Git parsing, strict UTF-8 and NFC,
  control-character rejection, normalization/casefold collision rejection, and
  adversarial path fixtures.
- Assigned canonical terminology reconciliation to chunk 01 for README,
  glossary, and architecture lockdown while retaining zero-trust loop
  terminology; this additive planning intake does not edit those files.
- Set 120-second hosted limits for each property suite and a 12-minute command/
  15-minute job budget plus two-minute critical-path cap for mutation testing.
- Required complete transitive hash locks and `--require-hashes` installation
  for assurance tools.
- Removed trailing blank lines and unified the cutover rule across every artifact.
- Replaced broad initiative allowlists with explicit per-chunk contract, status,
  internal evidence, trust-bundle, external-response, and specialized proof paths.
- Required duplicate JSON object-key rejection, exact signed discovery
  provenance, and a deterministic lossless review-log migration snapshot and
  32,768-byte UTF-8 index ceiling.
- Closed the file-history grandfather bypass: only chunks signed-active at the
  exact cutover may finish under an event/identity/path/blob-bound record;
  stopped, new, cancelled/restarted, and post-cutover work require schema.
- Reconciled the future mutation contract to current exact-custody semantic
  lanes while retaining the earlier shard topology as historical discovery.

## Concurrent Initiative Reconciliation

- Historical discovery pinned ART-03, AUTH-10C, and REV-03P exactly.
- Final reconciliation pins current main `a04fd1a0a623b7150ec40c9934a9982f80a2dce7`
  and signed-state tip `33edd1a682ea5fe5ea973870f89bdd3a75a63da3`.
- ART is stopped at PLAN2, AUTH is stopped at 11, and REV-03P remains active.
- AUTH property work starts only from the then-current canonical AUTH result.
- CON remains stopped; its unexplained local PDF deletion is not adopted.
- Dormant QUALITY work and stale external PRs remain discovery input only.
- Every implementation boundary repeats exact-main, signed-state, and path-overlap checks.

## Commands Run

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Results

- Planning merge intent passed for `WS-ENG-008-PLAN`.
- 100 Agent Gate tests passed.
- Markdown links passed for all 16 changed planning Markdown files.
- Stale wording and exact diff integrity passed.
- The reviewed diff is one additive initiative tree plus one merge intent.

## Remaining Risks

- Any concurrent PR may advance `main`; the planning PR must reconcile and rerun
  exact evidence before merge if its base changes.
- Tool choice and hosted runtime remain implementation-chunk decisions inside
  the reviewed dependency, evidence, and timeout boundaries.
- Planning merge grants no implementation authority. Chunk 01 still requires a
  separate signed start after canonical post-merge reconciliation.
- The prior Backend failure belonged to the retired dependency/workflow state.
  Exact-head Backend CI must pass again against current main before merge.
