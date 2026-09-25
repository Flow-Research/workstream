# WS-QUAL-003-16 — Behavior-first test evidence: AUTH audit and diagnostic coverage

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace misleading and mixed AUTH test evidence with
  exact, behavior-owned proofs while removing genuinely unreachable or
  test-owned scenarios. Retire percentage-based CI coverage quotas while
  keeping complete behavior and real integration verification blocking.

## Intent

Audit tests against observable behavior and failure boundaries, removing only
proof that is unreachable, test-owned, duplicated at the same effective layer,
or enforcing a retired percentage quota. Keep all meaningful behavioral and
integration checks blocking; coverage percentages are diagnostic only.

## Findings and decisions

- A decoded cursor-size test constructed a canonical value that exceeded the
  encoded-input cap first, so it never reached the decoder branch it named.
  Remove only that unreachable case; retain the exact encoded-length rejection.
- The admin decision-mutation matrix used an invalid reason digest, allowing an
  earlier digest check to mask the authority-binding variants. Bind the digest
  to the actual reason and retain all sixteen issue/revoke substitutions.
- One 665-line project-role PostgreSQL test combined issue, revoke,
  already-granted denial, and cancellation/retry. Split it into five focused
  tests. The former “unique-index loser” never inserted; the new fallback test
  must observe `uq_project_role_grants_active_exact_role` and prove no losing
  effects. The cancellation test observes a genuine lock wait and same-key
  retry.
- One 504-line prepared-transaction test simulated participant/evidence errors,
  timeout, commit cancellation, and rollback inside its own callbacks. Its
  timeout only wrapped a test-created event, mocked commit bypassed SQLAlchemy,
  and the test itself performed rollback. These are not additional Workstream
  behaviors. Remove it and rely on production-boundary evidence below.
- Coverage was also being used as a proxy for correctness: Backend and MCP
  workflows failed below percentages and Backend repeated selected tests solely
  to satisfy focused percentage floors. Current policy is that coverage is
  diagnostic only; all selected tests, API drills, real PostgreSQL/S3, failure
  propagation, and exact-head evidence remain blocking.
- The percentage/configuration/evidence/CLI surface in `coverage_policy.py`
  had no live consumer outside its quota-specific tests. Retire that dead code
  while retaining shared skip/xfail syntax analysis and the SQLAlchemy tracing
  accuracy regression used by structural policy.
- Five workflow snapshot tests enforced retired percentage floors or duplicated
  proof already owned by the complete semantic-lane catalogue. Remove only
  those assertions after confirming their modules remain in the full lane
  inventory; retain recursive inventory, exact execution custody,
  empty-selection rejection, failure propagation, and cleanup checks.

## Bounded change

### Allowed

- `backend/tests/test_authorization.py`: correct the cursor/decision inputs and
  remove only the unreachable cursor case and synthetic transaction aggregate.
- `backend/tests/authorization/project_roles/`: the five focused PostgreSQL
  issue, revoke, unique-constraint, lifecycle, and cancellation/retry tests and
  their minimal owner-scoped fixture.
- Existing real proof owners, assertion maps, and `.ci/auth-boundaries/`
  structural debt ledger, plus this record and its overview link.
- `.github/workflows/backend.yml` and `mcp.yml`, lane catalogue/CI integrity
  tests, the shared syntax owner in `coverage_policy.py`,
  `scripts/test_lightweight_agent_gates.py`, and directly affected current
  guidance in `AGENTS.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`,
  `.agents/skills/`, `docs/`, and Commitrail.

### Prohibited

- No product code, API/schema, migration, semantic-lane selection, infrastructure
  service, full-suite execution, PostgreSQL/S3 integration check, or unrelated
  test changes. No coverage percentage may block CI or be described as a quality
  requirement.
- No deletion or weakening of a distinct authorization, lifecycle, denial,
  evidence, rollback, lock, concurrency, or replay behavior.
- No arbitrary test-count target or replacement with end-to-end-only coverage.

## Retained proof

| Invariant | Final proof |
|---|---|
| Encoded cursor bound rejects oversized input before decoding | Existing malformed-input cases in `tests/test_authorization.py` |
| Decision mutation checks reach the intended AUTH matcher | The sixteen valid-digest issue/revoke substitutions and their deny-consumer checks in `tests/test_authorization.py` |
| Project-role issue/revoke bind exact authority, lifecycle, and transaction facts | `tests/authorization/project_roles/test_lifecycle_postgresql.py` |
| Active-role uniqueness conflict has only denial effects | `tests/authorization/project_roles/test_constraint_postgresql.py` captures the exact constraint |
| A real canceled actor-lock wait permits exact same-key retry and one committed evidence pair | `tests/authorization/project_roles/test_cancellation_postgresql.py` |
| Real caller state and AUTH evidence commit/roll back together, including failure after evidence write | `tests/projects/guide_compilation/finalization/test_authorization_postgresql.py::test_concrete_finalization_is_atomic` and `::test_finalization_failure_rolls_back_all_effects` |
| Public actor read fails closed before lifecycle touch when AUTH evidence fails | `tests/actors/test_self_api.py::test_actor_self_evidence_failure_is_retryable_before_touch` |
| Prepared dependency rollback and consumed-handle single use | `tests/test_authorization.py::test_prepared_dependency_rolls_back_every_transaction_failure` and `::test_prepared_exact_consume_remains_spent_after_cancellation` |
| All backend test modules execute in declared semantic lanes | The eight-lane catalogue recursively matches all discovered modules; newly split project-role PostgreSQL tests are assigned to existing partitioned shared-foundation lanes |
| Backend and MCP behavior/integration checks remain gates without percentage quotas | CI integrity tests assert no `fail-under` option; exact Backend lane custody and API contract drill, plus MCP lint/typecheck/test/build/package-independence, remain required |
| Coverage remains diagnostic, not a success threshold | Backend reports aggregate coverage and hosted telemetry; MCP reports pytest-cov diagnostics without a quota |

The combined assertion map contains 67 exact old assertion dispositions from the
two decomposed/retired PostgreSQL functions. The unreachable cursor case has no
database assertion map because it was not part of the frozen oversized-test
ledger; its source-boundary reasoning and surviving encoded-length proof are
recorded here.

## Acceptance criteria

- [x] Impossible decoded-size test removed; encoded boundary remains.
- [x] All sixteen authority mutations use a valid matching reason digest.
- [x] Mixed project-role test replaced by five independent PostgreSQL cases;
  unique fallback requires the exact database constraint.
- [x] Synthetic transaction aggregate removed; all 67 old assertion spans have
  exact dispositions in the combined assertion map.
- [x] Structural ledger, full collection, focused local tests, formatting,
  lint, markdown-link, stale-wording, and diff checks pass.
- [ ] Hosted Backend PostgreSQL and MCP workflows pass the exact PR head.
- [x] All eight semantic lanes and complete-run custody remain blocking; no
  failure is skipped, hidden, or replaced with coverage-only execution.
- [x] `docs/roadmap_status.md` reflects behavior proof as the quality contract;
  product capability and API exposure remain unchanged.

## Risk and review routing

- Risk: L1 — AUTH test-evidence deletion/decomposition and explicit retirement
  of CI coverage quotas; no product runtime change.
- Review inspects current production owners, retained test boundaries, assertion
  custody, CI execution custody, and updated contributor guidance without broad
  reviewer fan-out.
- Human review focus: confirm removed tests did not own distinct behavior, all
  surviving PostgreSQL tests remain on hosted lanes, and coverage cannot turn a
  failing behavior check green or vice versa.

## Evidence

| Claim | Proof | Result | Remaining uncertainty |
|---|---|---|---|
| Full backend collection | `uv run pytest --collect-only -q` | 7,845 tests collected; exit 0 | Collection is not execution; the count is not a target. |
| Focused prepared-service checks | Prepared dependency rollback and consumed-handle tests | Four non-DB cases passed | Does not execute PostgreSQL. |
| Structural debt and assertion custody | `uv run python -m scripts.test_structure_boundary validate --policy ../.ci/auth-boundaries/TEST_STRUCTURE_POLICY.md --ledger ../.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` | Pass; combined 67-assertion map validates | Semantic behavior and PostgreSQL execution remain hosted gates. |
| Formatting, lint, markdown, stale wording, and diff | Ruff, repository link/stale scans, and `git diff --check` | Pass | None for static checks. |
| Local PostgreSQL | `WORKSTREAM_TEST_DATABASE_URL` presence check | Not configured | No local database execution is claimed. |
| Lane ownership after test split | `uv run pytest -q tests/test_ci_lane_catalogue.py` | Passed after assigning all three new modules to existing semantic lanes | Hosted execution confirms real PostgreSQL custody on exact PR head. |
| Quota retirement does not weaken test execution | Workflow inventory and CI-integrity tests | No positive coverage threshold; full lane, API, PostgreSQL/S3, MCP test/typecheck/build and evidence-custody commands remain | Exact-head hosted workflows are still required. |

## Coverage-quota retirement accounting

- Remove four Backend quota-only reruns; selected modules remain in complete
  project semantic lanes, including real PostgreSQL variants.
- Remove five workflow snapshot tests asserting retired floors or duplicate
  invocations. Preserve their useful integrity claims as diagnostic-only and
  complete-lane-membership assertions.
- Retire percentage-specific helpers and tests from `coverage_policy.py` while
  retaining shared syntax/skip detection, its structural owner, and the real
  SQLAlchemy tracing regression.
- Remove five duplicate `weak_python` architecture cases because the canonical
  lexical syntax-owner matrix retains the same proof; keep path-selection and
  integration coverage.
- Total retired: 94 tests (89 quota/dead-policy tests and five verified
  duplicates), with two small diagnostics/completeness contracts replacing
  useful integrity checks. This count is disposition accounting, not a target;
  this slice does not claim the remaining suite is fully audited.
