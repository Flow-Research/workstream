# WS-QUAL-003-05 — Detach PROJECT guide and bundle fixtures from test collection

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: Move the complete guide/bundle setup dependency graph
  into cohesive PROJECT support modules without changing product proof.

## Intent and current behavior

Continue the behavior-first test audit after the seven-lane CI rebalance.
At main `7105dda1`, `backend/tests/test_projects.py` contains 15,141 lines.
`projects/test_locked_policy_context.py` imports its guide and bundle helpers
from that collected test module. Client isolation was already extracted in 03;
the remaining helper graph spans guide creation, diagnostic/verified sufficiency,
submission-policy approval and post-submit fixture persistence.

This slice audits and isolates that setup graph, not every PROJECT test.
Existing legacy PaymentPolicy prerequisites still exist in runtime and database
guards. Their age alone does not justify deleting their setup or assertions.
Likewise, fixture-generated outputs do not prove real agent execution.

## Bounded change

### Allowed

- This record and `OVERVIEW.md`: durable scope, findings and next boundary.
- `backend/tests/test_projects.py`: remove selected helper definitions, import
  their canonical support owners, and remove newly unused imports only.
- `backend/tests/projects/guide_fixtures.py`: `complete_guide_payload`,
  `create_project`, `create_guide`, `add_project_manager_admin_grant`,
  `source_snapshot_payload`, `create_source_snapshot`.
- `backend/tests/projects/submission_policy_fixtures.py`:
  `project_submission_artifact_policy_body`, `create_sufficiency_report`,
  `create_submission_artifact_policy`, `approve_submission_artifact_policy`,
  `load_pre_submit_checker_policy`, `force_pre_submit_checker_policy_pending`.
- `backend/tests/projects/post_submit_fixtures.py`:
  `create_generated_post_submit_setup_output`, `approve_post_submit_checker_policy`.
- `backend/tests/projects/policy_bundle_fixtures.py`: `create_approved_policy_bundle`.
- `backend/tests/projects/test_locked_policy_context.py`: import helpers directly
  from their new owners; leave test bodies and session/transaction flow unchanged.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: reconcile changed monolith
  locations/hashes from inventory; no new or growing debt.

### Not allowed

Production, migrations, workflows, lane catalogue, dependencies, grants/actions,
API activation, test selection, skips, coverage floors, or fixture transaction
and authorization changes. No global conftest, compatibility wrapper or support
module importing a collected test. Do not add tests only to inflate coverage.

## Design and decisions

Use four cohesive support files, each below 500 lines. Keep all 15 helper ASTs,
defaults, assertions, commit/flush order and dependency bindings unchanged.
Guide setup owns its project-scoped grant and source metadata; submission-policy
setup owns diagnostic/verified prerequisites and effective/pre-submit results;
post-submit setup owns its existing generated fixture rows. Bundle composition
imports those owners in one direction. The deterministic agent fake imports the
same relocated policy-body builder through the monolith's ordinary consumer import.
No wrapper exports or module-wide fixture discovery are added.

Do not conflate the existing fixture's generated post-submit result with worker
execution proof. Preserve the separate real worker tests and locked-context
PostgreSQL tests. Broadly rewriting historical setup while moving it would hide
behavior differences, so deeper helper simplification is deferred explicitly.

## Acceptance criteria

- Every moved helper has an AST-identical body, signature and decorator list;
  all referenced globals resolve to the same functions/classes or module objects.
- Every existing test body, decorator and parameter case is unchanged.
- The locked-context module and new support files import no collected test
  module, directly or transitively. New support imports are acyclic.
- Existing client fixture discovery, cache teardown and database isolation remain
  unchanged; no autouse scope expands.
- All four support files are below 500 lines, with no new structural debt.
- Hosted exact-node manifests retain every baseline case exactly once; full
  PostgreSQL, race, rollback, global and subsystem coverage gates still pass.

## Risk and review routing

- L1: shared security-sensitive database fixture relocation, no product change.
- Before implementation: focused plan review of dependency closure and evidence.
- Final QA/test-delta checks assertion and fixture preservation; architecture/
  reuse checks owner graph; CI-integrity checks full hosted selection and isolation.
  Combine related tracks proportionately, not all nine reviewer specialties.
- Human focus: no lost tests or changed grants/transactions, honest distinction
  between setup isolation and completed semantic audit.
- Size exception: relocation dominates; compare exact helper/test ASTs rather
  than treating moved source as new product implementation.

## Evidence

| Claim | Required proof | Boundary |
| --- | --- | --- |
| Helpers retain behavior | AST/global-binding comparison against main | Structural preservation, not database execution |
| No test loses assertions | Exact function/decorator AST comparison | Test delta |
| Independent support imports | Fresh-process import with a trap rejecting test_projects; import graph inspection | Composition |
| No hidden collection change | Hosted baseline/final exact node manifest equality | Full hosted selection |
| Database behavior preserved | Hosted locked-context and full PROJECT consumers, including independent-session lock tests | PostgreSQL and concurrency |
| No new debt | Existing inventory and structural validator; Ruff; file counts | Structure |

Use focused local pure/collection checks, not full local backend execution.
Hosted CI owns PostgreSQL and coverage. An in-memory reintroduced test-module
dependency must fail the import trap; this probe tests dependency isolation,
not product behavior. Run Commitrail, Markdown/stale scans and diff checks.

Implementation inspection preserves all 15 helper ASTs and their recursively
referenced global bindings, mapping moved-function references to their single
new owners. All retained monolith definitions and locked-context definitions,
including decorators and parameter rows, are AST-identical. Fresh-process support
imports pass with a trap rejecting collected-test dependencies; deliberately
reintroducing `import test_projects` is rejected at that trap. No test is removed.
The support modules contain 193, 224, 123 and 80 lines; the monolith shrinks from
15,141 to 14,617 lines. Existing oversized test bodies remain audit work, not
debt falsely marked retired. Hosted execution custody is recorded on the PR.

## Review findings

No test deletion is justified by this dependency extraction. The broader
semantic audit and oversized-test decomposition remain open.
Plan inspection confirmed the helper graph and monkeypatch/global-binding
strategy are feasible; similarly named TASK helpers are not equivalent reuse
targets because their states, return projections and customization differ.

## Reconciliation

- Current source: PR #369 merged at `7105dda1`; retain its seven-worker runner.
- Next usable boundary: continue PROJECT behavior audit and cohesive test-body
  extraction, then AUTH; POL-04A2 stays paused.
- Remaining risks: helper relocation can change global/monkeypatch bindings even
  when bodies match; inspect bindings and require full hosted consumers.
