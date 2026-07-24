# Discovery: WS-ENG-008 — Repository-Native SDLC Assurance

Discovery was performed read-only against trusted `main`
`bcf1292e1a591e3e84bf8ee212ee7191d80741fa` and signed
`automation/loop-memory` tip
`8affe98a0b877ba79abf9d23f86013f838985dcf` on 2026-07-24.

## Current behavior

- `scripts/check_internal_review_evidence.py` discovers changed files, resolves
  required reviewer tracks, binds reviewed SHA provenance, and restricts
  post-review changes. It does not parse or enforce contract path scope.
- `.agent-loop/templates/CHUNK_CONTRACT.md` requires human-readable allowed and
  forbidden sections without a machine-readable schema.
- Some historical chunks use one-off shell regexes or reviewed-scope manifests;
  there is no reusable canonical implementation.
- `.github/workflows/agent-gates.yml` runs evidence, merge-intent, Markdown,
  stale-contract, and regression gates. No workflow uses `schedule`.
- `scripts/update_post_merge_memory.py` and
  `scripts/check_loop_memory_state.py` already verify signed-state semantics and
  closed-tree integrity during merge/start workflows.
- `.codex/agents/` contains senior, QA, security, product/ops, architecture, CI,
  docs, reuse, and test-delta reviewers. No explicit adversarial proof contract
  exists.
- `scripts/agent-gate-requirements.txt` and `backend/pyproject.toml` contain no
  Hypothesis or mutation-testing dependency.
- Backend CI fans out four isolated shards, recombines exact artifacts, and
  blocks at 78 percent global coverage plus multiple 90 percent protected
  subsystem floors.
- `.agent-loop/REVIEW_LOG.md` is 147,017 bytes and 2,846 lines. Detailed review
  evidence also lives under initiative `reviews/` directories.

## Relevant files and modules

| Area | Existing surfaces | Gap |
|---|---|---|
| Contract enforcement | `.agent-loop/templates/CHUNK_CONTRACT.md`, `scripts/check_internal_review_evidence.py`, `scripts/test_agent_gates.py` | No universal typed path delta enforcement. |
| Signed memory | `scripts/update_post_merge_memory.py`, `scripts/check_loop_memory_state.py`, `.github/workflows/loop-memory*.yml` | No independent read-only schedule. |
| Reviewer routing | `.agent-loop/policies/routing-policy.md`, `.codex/agents/*.toml`, `.agents/skills/risk-router/` | Adversarial attempts are implicit rather than stable evidence. |
| Property tests | Loop-memory tests and authorization tests | Extensive adversarial examples, no generated invariant exploration. |
| Mutation testing | Backend coverage workflow and coverage policy | Coverage measures execution, not fault sensitivity. |
| Review memory | Root `REVIEW_LOG.md`, initiative review directories | Root narrative grows linearly and duplicates detail. |

## Concurrent initiative reconciliation

| Initiative | Signed state at discovery | Concurrent repository state | ENG-008 rule |
|---|---|---|---|
| `WS-ART-001` | `WS-ART-001-03` active | Dedicated clean worktree; no PR yet | Do not touch ART application or artifact-custody surfaces. Reconcile before every ENG-008 PR. |
| `WS-AUTH-001` | `WS-AUTH-001-10C` active | PR #194 open; local repairs differ from its published head and Backend CI is failing | AUTH property chunk waits for AUTH to merge or stop, then rebases on its canonical result. |
| `WS-REV-001` | `WS-REV-001-03P` active | PR #195 open and green at discovery | Avoid project/review runtime files and reconcile its merge before later test work. |
| `WS-CON-001` | stopped at `02A`, next `02B` | Worktree has an unexplained local PDF deletion | No adoption or modification; deletion remains outside ENG-008. |
| `WS-QUAL-001` | absent from signed state | Two stale local worktrees; no current authority | Treat all QUALITY commits as discovery input only; mutation work starts from current main under ENG-008. |
| External PRs #62, #138, #149 | no active signed initiative authority | stale, conflicting, or missing current gates | Never merge as ENG-008 authority; inspect only as preserved proposals when relevant. |

## Existing tests and gaps

- Agent Gate tests strongly cover merge intent, evidence, workflow pinning,
  coverage floors, signed state, and planning intake.
- Loop-memory tests already contain mutation matrices and replay/collision
  cases, but generated state-space invariants are not property-tested.
- Authorization tests cover deny-default and action ownership through examples;
  generated unknown/cross-resource/lifecycle combinations are not centralized.
- No test currently proves that every ordinary PR path is permitted by the
  signed contract's machine-readable scope.
- No scheduled proof detects later automation-branch tampering between events.
- Coverage evidence cannot show whether assertions kill plausible behavioral
  faults.

## Dependencies and integrations

- PyYAML is pinned for Agent Gates, but JSON is preferable for the first scope
  schema because it avoids YAML coercion and duplicate-key ambiguity.
- Hypothesis would be a new test dependency in Agent Gates and later Backend.
- A mutation engine would be a new development/CI dependency and needs a hashed
  or otherwise reproducible installation path.
- GitHub Actions scheduling runs workflow code from the default branch; the
  drift job must use read-only `contents` and `actions` permissions.

## Risks discovered

| Risk | Impact | Required treatment |
|---|---|---|
| Glob semantics differ across platforms | Scope bypass or false rejection | Define one closed repository-relative grammar and test traversal, symlink, rename, and case behavior. |
| Legacy contracts lack schemas | Immediate repository-wide failure | Exact cutover: every changed contract after the 01 merge requires schema; unchanged pre-cutover contracts alone are grandfathered. |
| Git permits control and normalization-colliding path bytes | Line/display parsing can conceal a delta | Parse NUL-delimited bytes, reject invalid UTF-8/control/non-NFC names and normalization/casefold collisions. |
| Scheduled audit becomes a repair path | Unreviewed signed-state mutation | Read-only permissions, no signing key, no publication command, regression-test workflow semantics. |
| Property suites are nondeterministic | Flaky required CI | Fixed profiles, stored counterexample text in evidence, bounded examples/deadlines, rerunnable seeds. |
| Mutation score is gamed | False assurance | Report eligible/killed/survived/timeout/excluded counts and classify survivors; do not use “kill one mutant.” |
| Review archive breaks references | Loss of durable evidence | Lossless byte-preserving archive, link map, root index, and stale-link tests. |
| Active PR advances main | Stale proof or merge conflict | Rebase/reconcile and rerun exact proof before each PR; signed contracts remain immutable. |

## Unknowns requiring later measured evidence

- Eligible module and runtime budget for the mutation pilot.
- Stable Hypothesis example/deadline profile under hosted runners.
- Archive period boundaries that produce useful index sizes without churn.
- Whether scheduled drift should alert through GitHub only or a later external
  operations channel; this initiative adds no external notification secret.

## Existing conventions to preserve

- One signed active chunk per initiative; distinct initiatives may run concurrently.
- One PR and one schema-v2 merge intent per chunk.
- Exact-current-main signed starts and human-owned specific-PR merge approval.
- Internal reviewer completion before publication; external checks supplement it.
- Automated Merge Memory owns the generated branch and never starts successors.
