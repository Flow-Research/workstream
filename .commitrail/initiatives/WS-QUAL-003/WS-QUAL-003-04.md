# WS-QUAL-003-04 — Rebalance hosted CI without reducing proof

- Durable disposition: Complete
- Intended merge outcome: Use the existing seven backend workers more evenly,
  preserving complete hosted execution before resuming the test audit.

## Intent

The migration baseline cleanup changed the cost distribution. On merged PR 368,
Backend run 34025242095 spent 11m14s in PROJECT, 8m21s in TASK, but only
2m03s/1m39s/1m45s in the three schema jobs. All 4,350 cases completed; global
coverage was 91.4124%. These are baseline observations, not a speed guarantee.
Each lane also collects and validates an inventory before its runner recollects
the same complete suite. Reduce avoidable wall time without deleting proof.

## Bounded change

Allowed files:

- `.github/workflows/backend.yml`: seven-lane matrix and matching artifact names;
  remove redundant standalone per-lane collection/validation, retaining runner
  collection and independent aggregate validation. Preserve lint and docstrings.
- `backend/scripts/run_test_lanes.py` and new `backend/scripts/test_lane_catalogue.py`: extract
  cohesive static inventory and partition definitions, then use two PROJECT,
  two TASK, two shared lanes and one schema lane. No runner execution redesign.
- `backend/tests/test_ci_test_lanes.py` and new `backend/tests/test_ci_lane_catalogue.py`:
  relocate catalogue/partition proof into a file below 500 lines, update exact
  owner expectations and add workflow/artifact parity and partition rejection
  cases. Existing runner/isolation assertions remain intact.
- `scripts/test_lightweight_agent_gates.py`: reconcile its exact lane-label
  assertions with the seven-worker topology, preserving all required fan-in,
  coverage, cancellation, MinIO and gate integrity assertions.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: reconcile moved spans only;
  no new debt or exemptions.
- `.ci/behavior-ownership/partition.v1.json` and
  `backend/scripts/behavior_ownership.py`: register only the exact new catalogue
  target in the shared group and approved-addition set; reconcile the authority
  digest without changing the protected base or permitting arbitrary additions.
- `docs/operations_backend_testing.md`, this record and `OVERVIEW.md`: describe
  the current execution topology and return boundary.

Prohibited: product/test-behavior removal, database/migration changes, dependency
changes, xdist, changed-files filtering, retries hiding failures, relaxed
timeouts, skips/deselection, weakened thresholds, evidence or isolation guards,
new service credentials, and extra workers. Global/subsystem thresholds stay
unchanged in this optimization; raising policy floors is a separate decision.

## Design

Keep the existing SHA-256 exact-node partition algorithm, applied within each
declared shared/PROJECT/TASK owner pair. Every schema node moves to one schema
lane; only isolated-runner self-tests retain the admin execution kind. Every
ordinary test continues through the database/role isolation runner. No worker
shares a PostgreSQL container or role with another worker.

Use a small explicit partition catalogue, not dynamic discovery or timing-based
selection. Reject missing, foreign or duplicated modules and mismatched owner
pairs. Preserve the independent final validator: it recollects the exact head,
rejects omitted/duplicated/unexecuted nodes, checks artifact digests and isolation,
and combines exactly seven coverage files. Remove only the earlier redundant
collection steps; the final required aggregate remains fail closed.

Preserve both module import and direct `python scripts/run_test_lanes.py`
execution through one catalogue and a conventional package-path bootstrap.
There is no alternate implementation or fallback catalogue.

Alternatives rejected: adding more runners increases aggregate cost; xdist
introduces shared fixture/concurrency changes; removing expensive integration
proof defeats the audit. API E2E retains its real aggregate-job services.

## Acceptance criteria

| Behavior | Named proof / custody |
|---|---|
| Seven workers and exact recursive module inventory | `test_committed_lanes_cover_recursive_inventory_exactly_once`, pure inventory |
| Explicit PROJECT/TASK/schema ownership | `test_measured_hotspots_have_explicit_semantic_owners`, contract inspection |
| Deterministic complete node partition for each owner pair | `test_owner_nodes_partition_deterministically`, pure per-owner cases |
| Schema nodes are not split and admin classification stays exclusive | `test_schema_nodes_share_one_lane`, existing manifest admin-kind test |
| Missing/foreign/duplicate modules reject | existing `test_inventory_fails_closed` |
| Wrong partition membership rejects even with correct duplicate count | `test_partition_rejects_wrong_owner_pair`, pure mutation probe |
| Matrix, download names and reporting names match catalogue | `test_workflow_lane_inventory_matches_catalogue`, workflow parsing |
| Direct-file runner imports the canonical catalogue | `test_direct_runner_cli_remains_runnable`, subprocess with no inherited PYTHONPATH |
| Only the exact catalogue ownership addition passes | `test_catalogue_partition_addition_is_bounded`, valid addition and arbitrary-sibling rejection |
| Missing/corrupt bundles and incomplete execution reject | existing `test_merge_test_lane_evidence.py` and `test_test_lane_evidence.py` proofs |
| Complete real execution, isolation and coverage | hosted Backend full suite + independent aggregate validation; no skipped or deselected nodes |
| No new oversized files/debt | structural inventory/validation; catalogue/test modules below 500 lines |

Compare final hosted manifest to baseline and explain every added/renamed tooling
case; existing product nodes must remain. Record slowest lane, aggregate runner
seconds and job durations before/after. Do not claim a speed improvement without
measured hosted evidence. Newly exposed fixture/order failures require diagnosis;
do not hide them or expand into product fixes without reviewing scope.

## Risk and review routing

L1: CI evidence/infrastructure. Plan review before implementation. Focused
CI-integrity/security, QA/test-delta and architecture/reuse/docs assignments;
no unrelated product reviewer fanout. Human focus: every test still executes,
ordinary/admin custody is unchanged, required aggregate cannot pass partial work,
and timing improvement is measured rather than assumed.

Size exception: the diff relocates the static inventory and existing collection
tests out of large files. Review original-to-new ownership and assertion parity;
this is one runner-topology change, not multiple product changes.

## Evidence

Local: focused CI catalogue/runner/merge/validator tests only, Ruff, structural
inventory and validation, behavior-ownership validation, Commitrail records, Markdown links, stale scans and
diff checks. Full backend/PostgreSQL/global and subsystem coverage run only on
GitHub Actions. Use a deliberate wrong-owner mutation to prove partition checks
fail; inspect existing missing-bundle and omitted-node negative tests for final
aggregation discrimination. Final exact-head checks/reviewer freshness and timing
artifacts belong in the PR summary, not a transient repository work queue.
Also run the root lightweight Agent Gates regression suite, including
`test_backend_uses_distributed_semantic_lanes_and_stable_fan_in`.

Plan review CI-PLAN-01/02/03 found the missing exact ownership registration,
direct-file import proof and ambiguous paths. This scope includes those narrow
corrections before implementation; it does not relax ownership validation.

Focused tooling proof changes from 81 to 88 cases: owner partitioning now has
three cases instead of one, plus wrong-owner rejection, direct CLI execution,
workflow parity and two exact-addition cases. The old three-schema partition
test is replaced by a single-schema completeness test. Catalogue/discovery/
manifest and collection-summary tests move to `test_ci_lane_catalogue.py`;
execution, isolation, cancellation and cleanup remain in `test_ci_test_lanes.py`.
No product test is removed. The new catalogue is 199 lines; the test modules
are 390 and 475 lines. Structural inventory finds no new or changed frozen debt.

The focused 88 cases pass. An in-memory mutant disabling only the owner-pair
comparison survives module-count validation but fails the new manifest rejection
test at `DID NOT RAISE`, proving the intended guard rather than fixture failure.
This is pure tooling evidence; hosted execution still owns real PostgreSQL,
coverage, complete node reconciliation and timing comparisons.

Implementation review CI04-ROOT-01 and hosted Agent Gates caught the root
lightweight test's stale three-schema labels. The same failure was reproduced
locally at its exact assertion. The reviewed scope correction includes that
consumer; its assertions now name all seven lanes. No fan-in or coverage guard
was removed. This was a missed consumer in discovery, not an infrastructure
outage or a reason to bypass the gate.
