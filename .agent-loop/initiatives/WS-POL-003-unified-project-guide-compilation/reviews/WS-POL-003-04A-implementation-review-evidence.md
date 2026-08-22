# WS-POL-003-04A Implementation Review Evidence

Date: 2026-08-22. Risk: L1. Outcome: PASS locally; human merge required.

## Review target and boundary

- Protected-main base: `116b36626d33c97e22a38bdbcb139ed56be084f2`,
  the unchanged merge of PR #355.
- Rebased implementation head: `a77776fb`.
- Rebased failure-containment remediation head: `b48cf518`.
- Rebased test-sensitivity head: `a730b396`.
- Post-review concurrency and CI remediation head:
  `0c11effdc3ddb9c3a110b77567fe6b8b38a12223`.
- Exact final semantic-test head:
  `0c11effdc3ddb9c3a110b77567fe6b8b38a12223`.
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
| Two callers could both load `reserved`, after which the loser could report `context_unavailable` instead of the winner's durable result | A valid advanced-state fence returns a non-dispatch receipt; the orchestrator reloads canonical state and converges on persisted, invalid-terminal, accepted-not-persisted, or unresolved recovery without a second provider call | Deterministic real-PostgreSQL races for persisted, invalid-terminal, and accepted-not-persisted winners; exact-lineage mismatch remains fail-closed |
| Candidate composition could call a legacy inference method | Reachability and poison-runtime tests require exactly one unified call and deny all three legacy calls | Static and executable call-graph proof plus killed legacy-call mutant |
| Context drift or projection leakage could create false setup truth | Exact attempt/context identity is checked and the hidden path writes no setup or policy projections | Real-PostgreSQL drift and downstream zero-count tests plus killed mutants |

## Focused and structural verification

- Focused runtime, contract, authorization, and ownership suite: 178 passed.
- Hidden-orchestrator real-PostgreSQL suite: 9 passed.
- Structural, authorization-boundary, lane-inventory, behavior-ownership, and
  test-structure validation: 166 passed.
- Post-review concurrency remediation passed 15 focused orchestrator unit tests,
  the isolated real-PostgreSQL orchestrator/service suite, and the complete
  238-node POL-04A selected coverage suite.
- Ruff, stale wording, Markdown links, chunk-state synchronization, and diff
  integrity passed.
- Repository docstring coverage passed at 80.2 percent after adding only
  bounded documentation to the new hidden orchestrator.
- Six seeded faults were applied temporarily, each exact discriminating test
  failed, each mutation was restored, and clean code passed afterward.

## Canonical Docker and semantic-lane proof

The exact final semantic-test head ran in Linux against real digest-pinned
PostgreSQL 16, Redis 7, and MinIO. The source mount was read-only. All seven
semantic lanes executed once against one common 4,151-node manifest.

| Lane | Collected | Completed | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| shared_foundations_a | 1,543 | 1,543 | 0 | 0 | 0 | 182.684 |
| shared_foundations_b | 1,506 | 1,506 | 0 | 0 | 0 | 189.418 |
| schema_contracts_a | 73 | 73 | 0 | 0 | 0 | 26.163 |
| schema_contracts_b | 3 | 3 | 0 | 0 | 0 | 9.911 |
| schema_contracts_c | 7 | 7 | 0 | 0 | 0 | 15.878 |
| project_lifecycle | 564 | 564 | 0 | 0 | 0 | 331.565 |
| task_lifecycle | 455 | 455 | 0 | 0 | 0 | 227.938 |

The independent merger and validator accepted exact custody of 4,151 of
4,151 nodes with no duplicates, skips, deselections, interruptions, or test
retries. Aggregate runner time was 983.557 seconds. Every lane reported its
owned database and MinIO cleanup complete.

Combined branch coverage passed all required floors:

- Repository: 91.20 percent; floor 78 percent.
- `app/interfaces/project_agents.py`: 96.88 percent.
- OpenAI project-agent adapter: 96.88 percent.
- AUTH guide-compilation adapter: 100 percent.
- PROJECTS guide-compilation public API files: 100 percent.
- Context builder: 100 percent.
- Orchestrator: 93.33 percent.
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
5. The first post-rebase lane launch pre-created the runner-owned metadata
   directory and was rejected before collection. It was excluded, and the
   canonical post-rebase run used a new evidence root.
6. The first post-review container invocation used the system Python rather
   than the image's `/opt/venv` and stopped before test execution. It produced
   no product evidence.
7. A diagnostic lane mount omitted other registered linked worktrees and
   failed one existing repository-protection test. The exact test passed after
   the canonical run mounted the complete linked-worktree topology read-only.
8. A display-only helper requested a non-existent summary field after all
   seven lanes, the independent validator, repository coverage, and every
   per-file coverage gate had passed. It did not alter the evidence.

## Review and delivery state

The first exact-code review closed architecture, simplicity, authorization,
provider-failure, lifecycle, test-integrity, CI, product, and documentation
findings at the rebased equivalent `b48cf518`. The post-publication review
finding about concurrent advanced-state recovery is closed at `0c11effd`.
Final exact-head review must ratify this evidence and the atomic completion
projections before the branch is eligible to publish. This record does not
authorize a push or merge.

The next boundary is AUTH-12B2 activation, followed by POL-04B live cutover.
