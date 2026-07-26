# External Review Response: WS-ENG-008-01

## Review source

- Pull request: `#203`
- Source: CodeRabbit
- Reviewed external head: `55dcad602f705cec7e6798234bdabb911e6683c3`
- Repaired implementation SHA: `848c6d972eba229478573faddb252eb534f8e5a8`

## Comments addressed

1. Provenance SHA consolidation: corrected the genuinely truncated signed-state
   commit to `6923f9ed4a8e48327d3aa4d046c8a8dc3a31ea3a` in status and evidence. The
   reviewed implementation SHA subclaim was dismissed: shell length and
   `git cat-file` prove `1ef5c3bd0bffedec684ae8b6cec2e6affbcb3b21`
   was already a resolvable 40-character commit.
2. Added the exact Ruff invocation to the authoritative Commands Run fence.
3. Mapped all nine reviewer tracks to the six sessions that performed them.
4. Replaced hard-coded template phase/risk values with explicit placeholders.
5. Added all conditional reviewer tracks and alignment guidance to the machine
   template example, plus a direct-runner regression.
6. Replaced the negated bootstrap check with a positive marker test and explicit
   `exit 1` for both trusted scope and evidence bootstrap paths.
7. Split validator imports from guarded execution so ImportError cannot refer to
   an unbound `LoopMemoryError`.
8. Normalized strict UTF-8 failures across contract, projection, tree, merge
   intent, and authenticated-ledger paths to stable `ContractError` failures.
9. Materialized both internal evidence code and its scope parser from trusted
   base after cutover, while an explicit absolute repository-root contract keeps
   all candidate Git/filesystem reads bound to `${{ github.workspace }}`.

## Comments deferred

None.

## Human decisions needed

None. All valid findings were inside the signed chunk contract. The false
reviewed-SHA subclaim was resolved from deterministic Git object evidence.

## Internal repair review

- senior engineering: PASS
- QA/test: PASS
- security/auth: PASS
- architecture: PASS WITH LOW RISKS
- CI integrity: PASS WITH LOW RISKS
- docs: PASS
- product/ops: PASS
- test delta: PASS
- reuse/dedup: prior PASS WITH LOW RISKS remains applicable; no new reuse blocker

## Commands rerun

```bash
python3 scripts/check_chunk_contract.py --base-ref origin/main --head-ref HEAD --state-ref origin/automation/loop-memory
python3 scripts/test_check_chunk_contract.py
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
ruff check scripts/check_chunk_contract.py scripts/check_internal_review_evidence.py scripts/test_check_chunk_contract.py scripts/test_agent_gates.py
git diff --check origin/main...HEAD
```

## Remaining risks

Only the previously accepted Low-risk consolidation opportunities remain:
duplicated reviewer/intent parsing and explicit trusted dependency lists. They
do not weaken this gate and require a separate future contract to consolidate.

