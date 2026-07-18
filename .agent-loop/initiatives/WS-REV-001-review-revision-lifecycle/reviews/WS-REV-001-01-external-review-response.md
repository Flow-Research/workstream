# WS-REV-001-01 External Review Response

## PR

- PR: `#145`
- Initial published head: `9ad0420e4c8f3ce0933a85fc75f133a340f91fcd`
- Reviewed repair candidate: `e239282e7d2a2b4d46137707f673f76fda55e4b8`
- Trusted base: `0ffdabf3dbb77e4e066683fde1a095d744ff1f43`

## Comments Addressed

- GitHub Agent Gates failed in `validate-merge-intent` because the declared
  successor title did not match the first heading of the existing
  `WS-REV-001-02` chunk contract.
- The successor heading now uses the canonical schema-v2 form and exactly
  matches `Locked Review Policy And Task Lifecycle Alignment` from
  `.agent-loop/merge-intents/WS-REV-001-01.json`.
- CodeRabbit's nine actionable comments were addressed: explicit pinned
  PlantUML precondition; four-source `--all` rendering; FinalAcceptance as an
  accept side effect; exact durable/final/current CheckerRun transition guards;
  complete TaskAssignment attribution; both ART v2 storage passages; exact
  checker routing outcomes; valid Markdown table cells; and explicit
  `auto_reject_after_limit=false` configuration with runtime enforcement owned
  by `WS-REV-001-02`.
- Its Markdown lint nit was addressed by reflowing the PR reference so a line
  no longer begins with `#143`.
- The revision scanner now permits the required false configuration while
  rejecting unquoted, quoted, JSON, and backticked truthy forms. The first
  repair candidate's Ruff formatting failure was also corrected.
- ART-02A3 PR #141 later advanced main. The branch merged it, resolved the sole
  glossary overlap by preserving both exact byte-store operations and narrow
  typed product capabilities, and corrected Ruff formatting in four merged ART
  gate assertions. Fresh exact-SHA internal review passed.
- CodeRabbit's later scope-verification comment was valid in requiring a
  fail-closed comparison. The repair intentionally retains trusted current main
  as the PR-scope base, documents why the original planning base is reserved
  for archival immutability, and compares exact added/modified statuses against
  a committed 71-entry manifest with rename detection disabled.
- Internal repair review then found that the first path-only manifest could not
  distinguish an approved modification from deleting the same path. The final
  status-aware manifest closes that gap; adversarial status-change, removal,
  rename-as-delete-plus-add, and unreviewed-addition probes all fail.
- AUTH-09C PR #146 later advanced main. The branch resolved the sole conflict in
  `scripts/test_agent_gates.py` by retaining all 80 main tests and seven REV
  tests: main's AUTH-09C/merged ART assertions are current, and REV's earlier
  ART phases remain fallback branches. The active REV contract now records
  AUTH-09C's exact 65-action, 12-active, 53-planned snapshot without activating
  any of the 24 unavailable REV dependencies.
- Internal plan review found three remaining records that called AUTH-09B's
  65/10/55 snapshot current. They now label AUTH-09B historical, AUTH-09C
  65/12/53 current, and future release counts dynamic.
- CodeRabbit's AUTH-09C follow-up correctly found that a committed-range scope
  comparison alone ignores staged, unstaged, and untracked content. The final
  verification now requires an entirely clean porcelain-v1 worktree before the
  exact 71-entry comparison; isolated probes cover all three dirty states.
- Its Markdown-heading finding was repaired by keeping `PR #146` inline, and
  its nit was addressed by naming the exact trusted-main and reviewed-code
  operands in the evidence.

## Comments Deferred

- None. The ART comment's highlighted lower passage was already correct, but
  its body identified an earlier raw `ArtifactStore` stack bullet; that earlier
  occurrence was also updated rather than dismissing the finding as stale.

## Human Decisions Needed

- None. The repairs preserve the approved Chunk 01 contract and do not start
  or implement Chunk 02.

## Commands Rerun

- `python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main`
- `python3 scripts/test_agent_gates.py`
- Ruff format/lint for both changed Python gate files.
- Stale artifact, authorization, review, and Workstream wording scanners.
- Markdown links, reference checksums, pinned PlantUML rendering, table-column
  checks, scope checks, and `git diff --check`.
- Exact `--name-status --no-renames` manifest comparison plus adversarial
  status-change, removal, rename, and addition probes.
- Exact-SHA plan gate and all nine required internal reviewer tracks.

## Remaining Risks

- Replacement GitHub checks and any CodeRabbit follow-up on the final repaired
  PR head remain required after push.
- Runtime concurrency, rollback, and AUTH/ART/CON integration remain owned by
  later implementation chunks.
