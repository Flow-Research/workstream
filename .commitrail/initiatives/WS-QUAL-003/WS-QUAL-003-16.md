# WS-QUAL-003-16 — Simplify and bind authorization test evidence

- Initiative: WS-QUAL-003
- Durable disposition: Planned
- Intended merge outcome: Replace misleading and mixed AUTH test evidence with
  exact, behavior-owned proofs while removing genuinely unreachable or
  test-owned scenarios. This single AUTH test audit covers cursor boundaries,
  project-role PostgreSQL mutations, and prepared-transaction failure proof.

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

## Bounded change

### Allowed

- `backend/tests/test_authorization.py`: correct the cursor/decision inputs and
  remove only the unreachable cursor case and synthetic transaction aggregate.
- `backend/tests/authorization/project_roles/`: the five focused PostgreSQL
  issue, revoke, unique-constraint, lifecycle, and cancellation/retry tests and
  their minimal owner-scoped fixture.
- Existing real proof owners, assertion maps, and `.ci/auth-boundaries/`
  structural debt ledger, plus this record and its overview link.

### Prohibited

- No product code, API/schema, migration, workflow, coverage policy, roadmap
  capability, or unrelated test changes.
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
- [ ] Hosted Backend PostgreSQL workflow passes the exact PR head.
- [x] No product capability or roadmap claim changes.

## Risk and review

- Risk: L1 — AUTH test-evidence deletion/decomposition; no runtime change.
- Review is self-contained to current production owners, retained test
  boundaries, and assertion custody. No additional reviewer fan-out was
  requested.
- Human review focus: confirm removed tests did not own a distinct behavior
  and that all surviving PostgreSQL tests execute on the hosted workflow.

## Evidence

| Claim | Proof | Result | Remaining uncertainty |
|---|---|---|---|
| Full backend collection | `uv run pytest --collect-only -q` | 7,845 tests collected; exit 0 | Collection is not execution; the count is not a target. |
| Focused prepared-service checks | Prepared dependency rollback and consumed-handle tests | Four non-DB cases passed | Does not execute PostgreSQL. |
| Structural debt and assertion custody | `uv run python -m scripts.test_structure_boundary validate --policy ../.ci/auth-boundaries/TEST_STRUCTURE_POLICY.md --ledger ../.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json` | Pass; combined 67-assertion map validates | Semantic behavior and PostgreSQL execution remain hosted gates. |
| Formatting, lint, markdown, stale wording, and diff | Ruff, repository link/stale scans, and `git diff --check` | Pass | None for static checks. |
| Local PostgreSQL | `WORKSTREAM_TEST_DATABASE_URL` presence check | Not configured | No local database execution is claimed. |

No roadmap update is needed: this is an AUTH test-evidence cleanup with no
change to capability, API exposure, delivered product scope, or dependencies.
