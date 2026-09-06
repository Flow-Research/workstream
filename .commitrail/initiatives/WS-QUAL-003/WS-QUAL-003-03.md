# WS-QUAL-003-03 — Isolate PROJECT fixtures and prove inactive locked-context denial

- Initiative: WS-QUAL-003
- Durable disposition: Complete
- Intended merge outcome: Extract cohesive PROJECT test support and close the
  inactive-project locked-policy repository proof gap without runtime changes.

## Intent and baseline

Continue behavior-first cleanup, not deletion to meet a count target. At main
`d95a70bb`, `test_projects.py` has 15,272 lines. Its client, settings and bootstrap
fixtures are imported by the 511-line `projects/test_locked_policy_context.py`.
That file mixes public value validation, fake-session lineage checks and real
PostgreSQL checks; its public-value test and database state matrix each combine
independent behaviors. `ProjectLockedPolicyRepository` already rejects projects
whose status is not active, but the stored inactive-project case is absent.

The audit must judge relevance before relocation: passing or old tests are not
automatically useful or obsolete. For this selected locked-context surface,
public immutability/closed errors, exact historical lineage, successor isolation
and database locking remain current contracts. Keep their distinct assertions;
replace mixed test bodies with focused cases. Remove an assertion only when its
behavior is retired or a named retained proof covers it at the same boundary.
No reduction quota overrides that decision. A larger named-test count after
splitting compound tests is not new product scope or evidence of more behaviors.

## Bounded change

### Allowed

- This record and `OVERVIEW.md`: record the next usable cleanup boundary.
- `backend/tests/projects/client_fixtures.py`: move `project_database_env`,
  `clear_project_settings_cache_after_test`, `project_client`, `auth_headers`,
  and `ensure_access_administrator_bootstrap` without changing authority/setup.
- `backend/tests/test_projects.py`: import those owner-scoped helpers and remove
  their old definitions and unused imports only.
- `backend/tests/projects/test_locked_policy_context.py`: keep real PostgreSQL
  lineage/successor/lock proof; split its compound state matrix and add denial
  with a stored inactive project and previously loaded active identity-map row.
- `backend/tests/projects/test_locked_policy_contract.py`: relocate pure public
  contracts and fake-session checks; split independent public-value assertions,
  preserving every old assertion, parameter and exception boundary.
- `backend/scripts/run_test_lanes.py` and `backend/tests/test_ci_test_lanes.py`:
  add the new contract module to existing PROJECT lane and exact ownership test.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`: regenerate exact inventory;
  remove the decomposed locked-context file debt, shrink monolith spans, add no debt.

### Not allowed

Production, migrations, authorization grants/actions, API activation, workflows,
dependencies, coverage floors, skips or selection weakening. Do not replace real
repository/concurrency tests with fakes or disable guards during assertions.
Do not move support to a global conftest or add test-module dependencies.

## Design and decisions

Keep fixture names, scope and environment/cache teardown exactly. Import the
autouse cleanup explicitly where it already applies, without expanding global
fixture discovery. Test support may seed cross-owner prerequisites as before;
it does not introduce a production cross-module interface.

Existing locked-policy integration tests still use monolith guide/bundle helpers.
Their transitive graph spans ART, setup and policy derivation; moving it all now
would obscure this bounded proof. Retain that existing debt explicitly; the new
contract module and client support import no test modules. Do not add aliases or
wrapper exports solely for compatibility.

For the new database test, build the existing fully valid active lineage and
resolve it successfully. Keep a Project instance loaded in an observer session,
release its transaction locks, then use a separate writer session to commit the
valid inactive `draft` state. Call the real repository in the observer and require
the exact bounded unavailable error, refreshed draft status, and no staged ORM
mutation. This tests persisted-state rejection and stale identity-map refresh,
not simultaneous revocation ordering. The existing independent-session lock test
continues to prove its narrower pre-submit-row lock boundary.

## Acceptance and proof mapping

- Client/settings/bootstrap function bodies and decorators are AST-identical
  after relocation; all existing PROJECT hosted journeys remain selected.
- Public contracts each have one primary behavior: immutable input copy,
  canonical hash, absent mutable projection, noncanonical/invalid JSON rejection,
  invalid mapping, bounded failure code, empty version, malformed digest and
  invalid facts state. Named `test_project_locked_policy_*` tests replace the
  mixed public test without discarding an assertion.
- Fake-session `test_locked_policy_repository_resolves_exact_current_and_superseded_policy`
  and `...rejects_invalid_lineage` retain all parameter rows and assertions.
  Add an inactive-project row for a focused guard-bypass mutation probe; this
  remains service proof and does not replace the database case.
- Separate PostgreSQL tests `...resolves_current`, `...resolves_superseded`,
  `...rejects_unknown_effective_policy`, and `...rejects_pending_pre_submit`
  preserve the original state-matrix assertions with independently valid fixtures.
- `test_locked_policy_repository_postgresql_rejects_inactive_project` uses the
  real stored valid lineage and independent writer described above. Active control
  must succeed before denial; no fake repository, arbitrary missing ID or disabled
  project-state guard may supply the negative result.
- `...does_not_substitute_successors` and `...serializes_race` retain exact
  assertions and transaction/cleanup order.
- Every new/rewritten file is below 500 lines; new helpers below 100 lines.
  No new frozen structural debt. Large monolith remains explicitly incomplete.
- Exact hosted node reconciliation explains splits/additions; no cases vanish
  without their assertions mapped. All global/subsystem coverage gates pass.

## Risk, verification and review

- L1: security-sensitive proof and shared fixture relocation, no product change.
- Plan review before implementation; QA/test-delta, security/CI integrity and
  architecture/reuse/docs tracks combined into three focused assignments.
- Human focus: fixture isolation, real negative reachability, preservation of
  PostgreSQL proof, and explicitly remaining test-module dependency.
- Size exception: relocation dominates the diff; compare function AST and exact
  case mappings rather than treating moved lines as rewritten product behavior.

Locally run the new contract module, two lane inventory tests, Ruff on touched
Python, structural inventory/validation, Commitrail, Markdown/stale scans and
diff checks. A temporary in-memory removal of only the project-active guard
must cause the new fake-session inactive row to fail its denial assertion.
Use hosted Backend for the full PROJECT fixture consumers, real PostgreSQL and
global/subsystem coverage. Do not run the full suite locally. Reviewers distinguish
local mutation discrimination from hosted repository custody, and do not infer
database behavior from the fake-session test.

## Reconciliation

- Baseline: merged PROJECT slice 02, PR #367, main `d95a70bb`.
- Next: continue PROJECT guide/bundle fixture decomposition and remaining
  PROJECT behavior audit, then AUTH. Product POL-04A2 remains paused.
- Most monolith bodies and the rest of the suite remain unaudited. The prior
  unrelated CON next-version completion coverage gap remains for the CON audit.
