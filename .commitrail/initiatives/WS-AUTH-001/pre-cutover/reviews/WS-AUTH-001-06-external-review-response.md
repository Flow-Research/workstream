# External Review Response: WS-AUTH-001-06

## Pull Request

PR #124 - Add canonical actor profile and identity resolution

CodeRabbit run: `099fb3fe-cd93-453a-9445-e0e483fe3b79`

## Comments Addressed

1. Migration identity-link UUIDs now seed from the canonical actor UUID instead
   of delimiter-ambiguous issuer/subject concatenation.
2. Downgrade copies current canonical display fields, including `null`, into
   existing legacy rows so a cleared contact email cannot be resurrected. The
   migration proof covers an updated display name and cleared email, and the
   operations contract records the intentional rollback scrubbing behavior.
3. Development and Flow verifier boundaries reject blank or padded identity
   anchors before persistence without normalizing distinct opaque values.
4. Legacy eligibility activation takes the exact external-identity advisory
   lock. The synchronized concurrency proof establishes actual lock waiting,
   ordered payload application, one row, and one audit per real transition.
5. Work-context claim, start, pre-submit-check, and submit affordances require
   both the current compatibility role and active eligibility, matching the
   mutation guards. Tests prove absent, disabled, and role-missing behavior plus
   submission denial with no submission, checker-run, or audit side effects.
6. The shared privileged database reset now has one test-owned implementation
   with an explicit canonical-actor option. All five affected fixture teardowns
   use nested `finally` blocks so reset failure cannot skip disposal or Alembic
   downgrade.
7. Canonical actor history-trigger reset tracks successful disable and always
   re-enables the trigger in a fresh transaction.
8. The compatibility allowlist uses Python AST structure and binds every direct
   adapter read and eligibility-gate call to its exact `TaskService` method.
9. The live API contract asserts that issuer, subject, and legacy roles are
   absent from the canonical actor response.
10. Touched Contributor-facing task prose no longer describes a human actor as
    a worker; legacy wire and storage identifiers remain under their declared
    later cutover.
11. GitHub Backend's only failure was the strict OpenAPI inventory retaining the
    pre-AUTH-06 counts and hashes. The contract now includes the two protected
    actor self-service operations without relaxing either fingerprint.

## Comments Deferred

None of the actionable comments were deferred.

## Non-Actionable Review Output

CodeRabbit's 53.8 percent docstring warning is a diff-local advisory rather than
the repository's configured quality gate. Existing public behavior and complex
helpers retain useful docstrings; narration-only comments were not added.

## Human Decisions Needed

None. The repaired downgrade now favors current canonical privacy state over
retaining stale pre-AUTH-06 display data, and the runbook makes that rollback
tradeoff explicit.

## Commands Rerun

```text
pytest focused AUTH-06 migration/concurrency/lifecycle behavior
pytest test_actor_legacy_classification.py test_actors.py --cov=app.modules.actors --cov-branch
pytest test_api_controls.py
python backend/scripts/api_contract_e2e.py
ruff check app tests alembic/versions/0020_canonical_actor_profile.py scripts/api_contract_e2e.py
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
python3 scripts/check_loop_memory_state.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

- Actor/classification behavior: 83 passed at 90.1031 percent branch coverage.
- Real Postgres API contract: passed through migration `0020` and the complete
  current task intake drill.
- Integrated engineering-loop gates: 71 passed; schema-v2 merge intent passed.
- GitHub Backend: 983 passed, one repaired OpenAPI inventory failure, and 83.11
  percent repository coverage; all 27 API-control tests pass after repair.
- All required internal reviewer tracks passed on reviewed code SHA
  `25d9455f6dca41b207a0ba3aaba8de9cc2683a17`.

## Remaining Risks

- Production migration still requires the documented quiesced deployment and
  non-owner runtime role.
- Rollback intentionally scrubs retained legacy display data that was not set
  canonically after AUTH-06.
- GitHub Backend owns the repository-wide suite and 78 percent baseline.

No GitHub thread is replied to or resolved by this evidence file. Thread writes
remain a separate explicit action after the repaired commit is pushed.
