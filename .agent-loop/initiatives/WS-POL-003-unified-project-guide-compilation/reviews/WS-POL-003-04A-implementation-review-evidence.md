# WS-POL-003-04A Implementation Review Evidence

Date: 2026-08-22. Risk: L1. Outcome: PASS locally; human merge required.

## Review target and boundary

- Stacked parent: `a1e2aaa3ba7e781d30ca7da09d3775af6659ec48`.
- Implementation head: `1042be52`.
- Failure-containment remediation head: `45bcebed46e96add5080e7599257903c75988539`.
- Test-sensitivity head: `4b16f3fc5a6532c05362edcdf0f3b717d0361d6b`.
- The chunk adds one hidden PROJECTS-owned execution command that accepts only
  an existing authorized compilation `attempt_id`.
- It adds no route, queue, Celery task, setup-ledger mutation, policy
  projection, approval, review, payment, or live product cutover.

## What the implementation proves

The hidden command reconstructs the exact immutable guide context, obtains a
fixed-service authorization decision, commits the existing one-shot dispatch
fence, and calls `compile_project_guide` at most once locally. A valid result
persists one immutable complete compilation. Observably invalid output is
terminal. Timeout, transport failure, unknown provider failure, cancellation,
or an already-fenced attempt remains unresolved and never redispatches.

The implementation reuses the existing POL-03B custody, ART material port,
canonical pre/post capability projections, AUTH adapter, and unified provider
method. It introduces no new table, migration, provider client, lifecycle,
framework, or cross-module debt.

## Findings closed during implementation review

| Finding | Resolution | Proof |
|---|---|---|
| A provider-raised `ValueError` could be mistaken for known-invalid output | Provider invocation and trusted result validation are separate; all unknown ordinary provider exceptions remain unresolved | Unit cases for provider `ValueError` and `RuntimeError`; no compilation or second call |
| Missing or revoked service authority could leak an internal AUTH error | Public AUTH unavailability is normalized to the safe `service_authority_denied` code before provider access | Real-PostgreSQL revoked-service test and bounded-error test |
| Repeated execution could call the provider behind an existing fence | The orchestrator returns the durable unresolved receipt whenever `dispatch_permitted` is false | Permanent replay test plus killed dispatch-guard mutant |
| Candidate composition could call a legacy inference method | Reachability and poison-runtime tests require exactly one unified call and deny all three legacy calls | Static and executable call-graph proof plus killed legacy-call mutant |
| Context drift or projection leakage could create false setup truth | Exact attempt/context identity is checked and the hidden path writes no setup or policy projections | Real-PostgreSQL drift and downstream zero-count tests plus killed mutants |

## Focused and structural verification

- Focused runtime, contract, authorization, and ownership suite: 178 passed.
- Hidden-orchestrator real-PostgreSQL suite: 9 passed.
- Structural, authorization-boundary, lane-inventory, behavior-ownership, and
  test-structure validation: 166 passed.
- Ruff, stale wording, Markdown links, chunk-state synchronization, and diff
  integrity passed.
- Six seeded faults were applied temporarily, each exact discriminating test
  failed, each mutation was restored, and clean code passed afterward.

## Canonical Docker and semantic-lane proof

The exact test-sensitivity head ran in Linux against real digest-pinned
PostgreSQL 16, Redis 7, and MinIO. The source mount was read-only. All seven
semantic lanes executed once against one common 4,147-node manifest.

| Lane | Collected | Completed | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| shared_foundations_a | 1,544 | 1,544 | 0 | 0 | 0 | 191.288 |
| shared_foundations_b | 1,505 | 1,505 | 0 | 0 | 0 | 247.785 |
| schema_contracts_a | 73 | 73 | 0 | 0 | 0 | 34.539 |
| schema_contracts_b | 3 | 3 | 0 | 0 | 0 | 10.418 |
| schema_contracts_c | 7 | 7 | 0 | 0 | 0 | 21.999 |
| project_lifecycle | 560 | 560 | 0 | 0 | 0 | 441.064 |
| task_lifecycle | 455 | 455 | 0 | 0 | 0 | 247.386 |

The independent merger and validator accepted exact custody of 4,147 of
4,147 nodes with no duplicates, skips, deselections, interruptions, or test
retries. Aggregate runner time was 1,194.479 seconds. Every lane reported its
owned database and MinIO cleanup complete.

Combined branch coverage passed all required floors:

- Repository: 91.21 percent; floor 78 percent.
- `app/interfaces/project_agents.py`: 96.88 percent.
- OpenAI project-agent adapter: 96.88 percent.
- AUTH guide-compilation adapter: 100 percent.
- PROJECTS guide-compilation public API files: 100 percent.
- Context builder: 100 percent.
- Orchestrator: 96.33 percent.
- Contracts: 99.00 percent.
- Service: 93.08 percent.

## Invalid operational attempts

The following attempts are excluded from product evidence:

1. A fresh image lacked the Git tooling required by repository-protection
   tests and was not used for the canonical run.
2. An initial Docker mount exposed the active worktree but not every Git-linked
   worktree path. One repository-protection test failed before the evidence
   root was discarded. The canonical run mounted the Git common directory and
   all registered worktree paths read-only.
3. A reporting-shell syntax error occurred after the first canonical lane had
   already written valid, passing evidence. It did not rerun or alter that
   lane.
4. The independent validator was first launched with a system Python that did
   not contain pytest. That invocation produced no validity claim; the same
   merged evidence passed with the tester image's pinned Python environment.

## Review and delivery state

The first exact-code review closed architecture, simplicity, authorization,
provider-failure, lifecycle, test-integrity, CI, product, and documentation
findings at `45bcebed46e96add5080e7599257903c75988539`. Final exact-head review
must ratify this evidence and the atomic completion projections before the
branch is eligible to publish. Protected main does not contain this work, and
no merge is authorized by this record.

The next boundary is AUTH-12B2 activation, followed by POL-04B live cutover.
