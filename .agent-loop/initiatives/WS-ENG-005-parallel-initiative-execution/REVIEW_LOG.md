# Review Log: Parallel Initiative Execution

> Archive only. This initiative is historical and closed. Current concurrency
> guidance lives in `CONTRIBUTING.md` and `../../CURRENT_STATE.md`.

- 2026-07-21: User approved replacing repository-global serialization with one
  active chunk per initiative and maximum safe cross-initiative concurrency.
- 2026-07-21: L1 plan review passed after requiring forward-compatible rollback,
  real-equivalent AUTH-active bootstrap proof, exact projection semantics, a
  three-initiative mixed-phase sequence, cross-initiative close isolation, and
  explicit separation of rebase from signed scope authority.
- 2026-07-21: Implementation removes only the three global-idle checks and
  retains target-initiative exclusion. Deterministic proof passes 208 tests, 89
  agent gates, updater/checker branch coverage at 90.22/90.12 percent, and a
  temporary real-state drill with AUTH-10A plus ART-02C3 concurrently active.
  Exact-SHA internal review remains.
