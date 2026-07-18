# WS-CON-001-PLAN3 External Review Response

## Review source

CodeRabbit review of PR #142, run
`26a5debe-60e5-445a-840c-f7155725fd90`, against `0302bcf...adf5cc1`.
Five unresolved consolidated threads and one PR-description warning were
triaged on 2026-07-17.

## Comments addressed

1. `PRRT_kwDOSwL_U86R1pF_`: added deterministic runnable verification commands,
   coverage targets, and explicit pass criteria to CON-01, 02A, 02B, 02C, 10A,
   10B, 10C, and 11.
2. `PRRT_kwDOSwL_U86R1pGB`: moved AUTH registration, ServiceIdentity/static
   authority, typed-context, custodian, and prepared-protocol ownership into
   approved prerequisites/handoff inputs for CON-02B, 10A, and 10B. Acceptance
   criteria now cover only CON-owned composition and behavior.
3. `PRRT_kwDOSwL_U86R1pGD`: moved contribution-policy action registration out
   of CON-04B. The hidden feature may consume reviewed AUTH ports, but AUTH
   alone owns later registration, evaluator integration, and activation.
4. `PRRT_kwDOSwL_U86R1pGE`: added deterministic runnable verification commands,
   coverage targets, and explicit pass criteria to CON-04B, 05A, 05B, 06, 07,
   08A, 08B, and 08R.
5. `PRRT_kwDOSwL_U86R1pGI`: moved CON-09B out of executable `chunks/` and
   corrected it from an incomplete “Chunk Contract” to a non-executable
   “Deferred Proposal.” It now has prospective risk, zero current allowed
   files, explicit prohibitions, exact-whitelist promotion checks, required
   reviewers, and a mandatory fresh replacement contract after separate
   human/ART/AUTH approval.
6. CodeRabbit description warning: the PR body is replaced with the complete
   PLAN3 trust-bundle structure after the reviewed repair is pushed.

## Comments deferred

None. CON-09B implementation remains intentionally deferred by product scope,
but the review concern about presenting an incomplete actionable contract is
addressed now.

## Human decisions needed

None for this repair. The human directed that all CodeRabbit findings be fixed.
Existing separate approval gates for CON-01, optional CON-09A/09B, and PR merge
remain unchanged.

## Commands rerun

```text
Markdown links: PASS (61 changed Markdown files before evidence refresh)
Stale Workstream wording: PASS
Stale authorization docs: PASS
Stale artifact contracts: PASS at foundation phase
Loop-memory state: PASS
Agent gates: PASS (80 tests)
Merge-intent validation: PASS
Bash syntax for every new verification block: PASS
Diff integrity: PASS
Repair backend/.github/scripts delta: none
Required exact-SHA internal tracks: PASS at a69fad3a32ad47e3bd60a79cd75f5867eefc52b3
```

The internal-review evidence gate is run in a clean worktree after this
provenance-only rebind commit; it must pass before push.

## Remaining risks

- Future implementation filenames and migrations must replace each contract's
  explicit placeholder without broadening its allowed scope.
- Focused pytest selectors are required to select at least one test; a zero-test
  selection is a failure, not a pass.
- CON-09B remains non-executable until a fresh replacement contract is
  separately approved and reviewed against then-current ART/AUTH boundaries.
- GitHub threads remain open until the reviewed repair is pushed; they are
  resolved only after the remote diff contains these fixes.
