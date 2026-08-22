# WS-POL-003-04A3 Implementation Review Evidence

Date: 2026-08-22. Risk: L1. Outcome: PASS locally; human merge required.

## Review target and boundary

- Protected-main base: `a95a0b02d7c546b2440f6b8dd8215a4be07671ff`.
- Exact semantic-test head: `8c719ec0ca25c14bcedd70450753cfa7807e8a45`.
- The chunk adds two hidden, route-unreachable PROJECTS operations that project
  one persisted unified compilation into the canonical sufficiency report and
  draft submission-artifact policy.
- It makes no model/provider call and adds no route, worker, queue, outbox,
  setup-row mutation, approval, effective policy, checker policy, or live
  cutover. Production authorization remains deny-default until AUTH-12J.

## Implementation outcome

Both projections reuse the immutable POL-04A compilation, locked ART material,
existing canonical product models, and action-specific authorization ports.
Each component has one deterministic output identity, content digest,
authorization decision, and immutable custody row. First execution creates one
canonical output; replay revalidates current authority and returns the same
receipt without a second event or product row.

The implementation uses one orchestration state machine and one pure payload
module. Splitting deterministic value construction reduced the orchestrator
below the repository's structural ceiling without adding a service, plugin
framework, generic component API, or duplicate lifecycle.

## Findings closed

| Finding | Resolution | Proof |
|---|---|---|
| Initial orchestrator exceeded the 1,200-line structural limit | Pure payload construction moved to `projection_payloads.py`; orchestration remained singular | Structural gate PASS; orchestrator 1,045 physical lines; payload module branch coverage 100% |
| Provider/runtime failures could be overclassified | Preflight, transaction, and persistent-conflict failures map only to closed public errors | Focused error-mapping and bounded retry tests |
| The new custody FK changes parent-ledger TRUNCATE behavior | The existing test now requires SQLSTATE `0A000` and both exact child/parent table names; UPDATE/DELETE retain the old trigger denial | Real-PostgreSQL request-operation test, 3/3 PASS |
| Snapshot-only reads could become ambiguous after generation reuse | The existing read orders by the unique setup generation; an unused exact-generation helper was removed | Real-PostgreSQL test with two rows and inverted timestamps proves generation 2 wins |
| A broad legacy repository missed the feature-file 90% floor | Dedicated 04A3 files retain at least 90%; the legacy file has a 78% non-regression floor and its changed method is fully executed | Canonical combined coverage and focused changed-method coverage |
| Unrelated repository tests were briefly added to inflate coverage | The padding test was removed before final verification | Final diff and exact 4,261-node manifest contain only the meaningful selection proof |
| A stale phrase still described the future cutover as a worker cutover | The documentation now describes the boundary as background-execution cutover | Stale-authorization documentation gate PASS |
| The projected policy admitted Cloudflare R2 before its storage boundary exists | R2 was removed from the v1 transform and contract; only local and S3 remain allowed | Focused payload tests, stale-artifact contract gate, and all seven semantic lanes PASS |

## Focused verification

- Focused implementation, migration, authorization, architecture, ownership,
  and lane suite: 341 passed.
- Request-custody compatibility test: 3 passed against migrated PostgreSQL.
- The two-generation repository selection test passed against migrated
  PostgreSQL and executed every changed statement in the selected method.
- Ruff, docstring coverage, authorization-boundary, behavior-ownership,
  test-structure, stale-wording, Markdown-link, atomic-state, and diff-integrity
  gates passed.

## Canonical semantic-lane proof

The exact semantic-test head ran in Linux against real PostgreSQL 16 and MinIO.
All seven lanes used one common 4,261-node manifest and ran sequentially.

| Lane | Collected | Completed | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| shared_foundations_a | 1,541 | 1,541 | 0 | 0 | 0 | 225.134 |
| shared_foundations_b | 1,508 | 1,508 | 0 | 0 | 0 | 229.071 |
| schema_contracts_a | 73 | 73 | 0 | 0 | 0 | 36.814 |
| schema_contracts_b | 3 | 3 | 0 | 0 | 0 | 11.185 |
| schema_contracts_c | 7 | 7 | 0 | 0 | 0 | 20.452 |
| project_lifecycle | 674 | 674 | 0 | 0 | 0 | 490.618 |
| task_lifecycle | 455 | 455 | 0 | 0 | 0 | 303.089 |

The independent merger and validator accepted 4,261 of 4,261 nodes with zero
duplicates, skips, deselections, interruptions, or retries. Aggregate runner
time was 1,316.234 seconds. Every lane reported successful database and MinIO
cleanup. The retained collect-summary, run-summary, and combined-coverage
digests are, respectively,
`f2748afa216a0707a707f20d0cdfcd05925b2d2c7ecbab5c3cd58d95f701220e`,
`b731f682ac00a20904b6792c8f4262130cfac8e52a7ba77ed4f52aa1602b4bc4`,
and `42dd3654b976425e51830f5564634f49dc1100ba6d47492c1db0a2e9863b2cf6`.

Combined branch coverage passed every required floor:

- Repository aggregate: 91.32%; floor 78%.
- Audit projection vocabulary: 95.69%.
- AUTH projection API: 100%.
- PROJECTS projection API: 100%.
- Projection models: 100%.
- Pure projection payloads: 100%.
- Projection repository: 96.98%.
- Projection orchestration: 95.59%.
- PROJECTS models: 100%.
- Broad legacy PROJECTS repository: 78.47%; non-regression floor 78%.

## Excluded operational attempts

The following attempts are not product evidence:

1. The first implementation exceeded the repository structural-file ceiling;
   the failed evidence was discarded before the pure-payload simplification.
2. One Docker run exposed only the active worktree, so an existing linked-
   worktree safety test failed. The canonical tester mounts the full registered
   worktree topology and the exact test passes.
3. An early exact-head run exposed the truthful PostgreSQL FK TRUNCATE message
   change. The contract and focused test were strengthened before rerunning.
4. A complete seven-lane run first stopped at the broad legacy repository's
   inappropriate 90% file floor. The unused API and coverage padding were
   removed; the final contract uses the reviewed targeted non-regression gate.
5. A reviewer mistakenly cleaned an untracked evidence directory during a
   later collection. No test lane completed in that attempt; reviewers were
   stopped before the exclusive canonical run.
6. The first hosted Agent Gates run exposed stale cutover terminology and then
   the deferred R2 storage scheme. Both findings were corrected and the full
   exact-head semantic proof was rerun; the failed hosted run is not product
   evidence.

## Review and delivery state

Architecture, simplicity/reuse, and test-integrity reviews passed the hidden
projection design. The exact semantic-test head contains the complete runtime,
test, and CI delta described here; publication still requires final exact-head
CI and human review. This record does not authorize merge.

The next delivery boundaries are POL-04A2 hidden setup finalization and
AUTH-12J projection authority; both depend on merged 04A3.
