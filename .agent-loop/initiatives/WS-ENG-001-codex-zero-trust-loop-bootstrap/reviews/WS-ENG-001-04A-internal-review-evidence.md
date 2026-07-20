# WS-ENG-001-04A Internal Review Evidence

Reviewed code SHA: `dcaa7091b8808acd086028bf517ffb9e5d2027d2`

Reviewed at: 2026-07-20T14:43:18Z

Reviewer run IDs: senior-engineering/architecture/reuse-dedup=`eng04_impl_arch`; QA/test/CI-integrity/test-delta=`eng04_impl_qa_ci`; security/auth/product/ops/docs=`eng04_impl_sec_ops`

Open sub-agent sessions: none

Valid findings addressed: yes

Reviewed against trusted main: `fe0e4492a7de8699c06a52921cbdaa8a1a22e567`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta.

## Deterministic evidence

- Python compilation passed for updater, checker, and agent-gate tests.
- Ruff passed for all three changed Python files.
- All 91 agent-gate tests passed with plugin autoload disabled.
- Branch coverage passed at 92 percent for `update_post_merge_memory.py` and 93
  percent for `check_loop_memory_state.py`.
- Merge-intent validation passed for `WS-ENG-001-04A`.
- Authored loop-state, stale wording, authorization, artifact, Markdown link,
  scope, dependency, test-delta, workflow-delta, and diff-integrity checks passed.
- No dependency, product runtime, migration, coverage threshold, required check,
  approval, or branch-protection behavior changed.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | Pass after fixes | None | Exact staged-tree validation closes the initial publication gap. |
| QA/test | Pass after fixes | None | Real Git integration and exact historical fixtures added. |
| Security/auth | Pass after fixes | None | No hostile-path, signature, secret, or write-authority bypass remains. |
| Product/ops | Pass after fixes | None | Existing and absent state branches have deterministic recovery. |
| Architecture | Pass after fixes | None | Existing ledger/render/sign/preparation abstractions are extended. |
| CI integrity | Pass after fixes | None | No gate weakening; exact workflow plumbing is executed in tests. |
| Docs | Pass after fixes | None | Closed tree, replay, root bootstrap, and stopped-state limits documented. |
| Reuse/dedup | Pass | None | Independent checker duplication remains intentional zero-trust proof. |
| Test delta | Pass | None | Additive proof; no assertions, skips, or thresholds weakened. |

## Findings resolved

Initial review found that the signed output directory was validated before
staging but the temporary-index Git tree was not compared to signed bytes. It
also found no executable Git-plumbing test, missing exact custody fixtures, and
an unborn-branch path that incorrectly assumed `HEAD`.

Repair `e5679d4c` adds staged-tree path/mode/blob validation before `commit-tree`,
real parented and root Git publication tests, unsafe-mode rejection, outside-
sentinel proof, exact AUTH-09E to ART custody to REV custody fixtures, and root-
commit workflow recovery. All nine tracks pass the repaired exact SHA.

## Remaining risk and gate

Hosted Agent Gates and human review remain. The automation workflow itself can
only be proven live after merge; its trusted replay must then produce the closed
signed tree. `WS-ENG-001-04B` remains inactive and requires a separate start.
