# Chunk Contract: WS-CON-001-05A - Legacy Economic Terms Cutover And Task Freeze

## Goal

Remove the retired guide-bound economic contract from every semantic consumer,
classify existing rows, and expose the CON-owned validation port used once when
a Project Guide is activated. The port returns the one active, published,
complete, binding-valid same-project ContributionPolicyVersion that PROJECTS
binds to the guide. This chunk supplies the required immutable FK/persistence
contract for the guide -> task -> assignment lineage, but owns no PROJECTS or
TASK command composition. Physical dead-schema removal belongs to 05B.

## Risk

L1 economic/task lifecycle/authorization; SLA P1.

## Allowed files

```text
backend/app/modules/contributions/{ports,service}.py
backend/app/modules/projects/{models,schemas}.py only the guide-bound ContributionPolicyVersion FK contract and legacy consumer removal
backend/app/modules/tasks/{models,schemas}.py only the task/assignment ContributionPolicyVersion FK contract and legacy consumer removal
backend/app/modules/checkers/{schemas,repository,service,runner}.py only legacy consumer removal
backend/alembic/versions/<next>_task_assignment_contribution_policy_freeze.py
backend/app/db/models.py
backend/tests/{test_contributions,test_projects,test_tasks,test_checkers,test_authorization,test_alembic,test_api_contract_e2e}.py
docs/spec_contribution_compensation.md
docs/architecture_data_model.md only exact implemented reconciliation
docs/operations_payment_reputation.md only implemented operations
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-05A.json
```

## Not allowed

```text
PROJECT guide-activation or TASK readiness/claim/assignment command composition
task-claim permission/grant/kernel implementation
ReviewLease or Review behavior; contribution/award creation
public policy routes; dead physical schema removal
fallback, alias, automatic conversion, or guessed historical rewrite
provider/artifact calls; unrelated checker behavior
```

## Acceptance criteria

- [ ] CON exposes one caller-session, flush-only validation port that locks and
  returns the one active, published, complete, binding-valid same-project
  ContributionPolicyVersion for guide activation. It contains no PROJECTS,
  TASK, role, claim, assignment, or revision composition.
- [ ] The persistence contract supports non-null
  `ProjectGuide.contribution_policy_version_id`, non-null
  `WorkstreamTask.locked_contribution_policy_version_id` before
  claimability, and non-null
  `TaskAssignment.submitter_contribution_policy_version_id`; exact FK and
  same-project constraints reject mixed lineage.
- [ ] Exact merged Submission.task_assignment_id lineage is preserved; no
  parallel submission identity is added.
- [ ] No runtime/API/setup/task/checker/review consumer treats retired guide-
  bound terms as current economic authority. A zero-consumer scanner proves
  remaining physical schema is unreachable until 05B.
- [ ] Missing/invalid policy fails guide activation with no guide/task/
  assignment/audit/outbox partial state. Later publication never updates an
  active guide, existing task, assignment, Submission, ReviewLease,
  ContributionRecord, or CompensationAward. A newly prepared task may inherit
  a newer version only through a newly activated guide generation. All tasks
  prepared from one active guide generation lock that guide's same version.
- [ ] Publish versus guide activation and binding-state versus guide activation
  pass both lock orders without deadlock or mixed versions.
- [ ] `WS-ARCH-001-03B` alone owns TASK readiness and claim composition. It
  inherits the guide-bound version onto the task before claimability, then
  copies the task lock onto the assignment without invoking CON at claim time.
  `WS-ARCH-001-03C` alone owns the later AUTH activation proof.
- [ ] Existing rows follow the approved deterministic classification and cannot
  enter new Review decisions without a valid freeze. Migration fails on
  ambiguity and downgrade refuses post-cutover data loss.
- [ ] Changed subsystems remain at least 90 percent; global floor remains 78.

## Verification

Execute the exact clean isolated CON-05A row in `../RUNTIME_VERIFICATION.md`,
replace its migration placeholder with the one new revision, then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_projects.py tests/test_tasks.py tests/test_checkers.py tests/test_authorization.py tests/test_alembic.py tests/test_api_contract_e2e.py -k '(policy or assignment or claim or migration or downgrade) and (freeze or rollback or race or lock or ambiguous or authorization or lineage)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/projects/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/tasks/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/checkers/*' --fail-under=90)
legacy_pattern='locked_''payment_''policy_version|payment_''policies|accepted_''payment_rule|revision_''payment_rule|rejection_''payment_rule'
if rg -n "$legacy_pattern" backend/app --glob '*.py' --glob '!**/models.py' --glob '!db/models.py'; then
  exit 1
else
  rg_status=$?
  test "$rg_status" -eq 1
fi
```

Pass requires a non-empty selected test set, upgrade and guarded downgrade,
exact guide/task/assignment/Submission lineage, full rollback on missing or
ambiguous policy, both publication/activation and binding/activation race
orders, no claim-time policy lookup, no runtime legacy-policy consumer,
repository coverage at least 78 percent in the same clean run, and every
focused report at least 90 percent.

## Review and stop

Required tracks: senior, QA, security, product, architecture, docs, reuse, test-
delta, and CI integrity. Stop if the guide/task/assignment persistence contract
or migration classification cannot be exact. Do not implement PROJECTS/TASK
composition or `task.claim` activation inside this chunk.

## Merge state

- Outcome on merge: `planned`
