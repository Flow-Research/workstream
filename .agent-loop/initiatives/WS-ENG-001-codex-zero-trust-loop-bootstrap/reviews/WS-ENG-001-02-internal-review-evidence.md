# Internal Review Evidence: WS-ENG-001-02

## Chunk

`WS-ENG-001-02` - Automated Post-Merge Memory

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 501890305167223fd50d42484adc75c6fae99bd2

Reviewed at: 2026-07-15T00:17:05Z

Reviewer run IDs: auth04b_final_eng/5018903, auth04b_final_qa/5018903, auth04b_final_security/5018903

After the reviewed SHA, only this review evidence, its trust bundle, the
external-review placeholder, and owning initiative status changed. No workflow,
generator, validator, test, policy, signing key, or merge intent changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None remaining | Exact integrated head retains coherent empty-state bootstrap, exact no-op validation, signed freshness, hostile-state rebuild, and current-main changes. |
| qa/test | PASS AFTER FIXES | None remaining | Sixty-three unique runner tests pass; the exact parent test union retains every automation and current-main artifact test. |
| security/auth | PASS AFTER FIXES | None remaining | Exact integrated head preserves trusted-default-branch replay, immutable intent, signing, expected-main binding, bounded cleanup, secret handling, and sole write ref. |
| product/ops | PASS AFTER FIXES | None remaining | The manager reviews one implementation PR; generated bookkeeping no longer creates a second review cycle. |
| architecture | PASS AFTER FIXES | None remaining | Generated state remains isolated from protected main and Workstream product/runtime authority. |
| ci integrity | PASS AFTER FIXES | None remaining | Existing gates remain; main now requires Agent Gates and Backend test with stale approvals dismissed. |
| docs | PASS AFTER FIXES | None remaining | Policy, skill, contract, runbook, status, chunk map, and review log describe the implemented trust model. |
| reuse/dedup | PASS AFTER FIXES | None remaining | The authority workflow reuses the exact canonical validator and one updater rather than a weaker duplicate path. |
| test delta | PASS AFTER FIXES | None remaining | Existing tests were retained; new behavior tests are runner-included and no assertions were weakened or skipped. |

## Valid Findings Addressed

- Replaced branch-selectable manual workflow execution with trusted-default-
  branch `repository_dispatch`.
- Replaced mutable PR-body authority with one strict merge-intent file fetched
  from the reviewed final head.
- Reconciled every first-parent merge from an immutable activation anchor so
  concurrency can drop events without dropping history.
- Selected required checks by start time so a newer pending rerun cannot be
  misreported as an older success.
- Added full ledger hash/schema/first-parent validation and exact rendered-state
  validation.
- Signed canonical files with Ed25519, bound final verification to protected
  main, and rejected replay of older valid signed snapshots.
- Rebuilt invalid, malformed, non-UTF-8, directory-backed, or symlinked state
  without following external symlink targets.
- Configured live main protection to require `agent-gates` and Backend `test`
  and dismiss stale approvals; pre-created the generated branch with linear
  history and deletion/force-push disabled.

## Evidence

```bash
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m coverage run --branch --source=scripts -m pytest -q scripts/test_agent_gates.py
python3 -m coverage report -m scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

Results:

- Plain-Python runner: 63 tests passed.
- Pytest: 63 tests passed.
- Branch coverage: updater 90.79 percent; independent checker 94.41 percent;
  combined 91.40 percent.
- Compilation, YAML parsing, stale wording, stale authorization, stale artifact,
  Markdown link, legacy loop-state, and diff integrity checks passed.
- No backend runtime file changed, so the multi-hour backend suite was not run
  locally; GitHub Backend remains required before merge.

## Remaining Risks

- Repository writers can append to the generated branch, but unsigned,
  malformed, or stale content is not canonical: verification rejects it and
  trusted automation rebuilds from protected-main history.
- Signing-key rotation requires a coordinated reviewed public-key change and
  repository-secret update. A mismatch fails closed before push.
- The first live workflow run remains external evidence and must pass before
  this process change is considered operationally proven.
