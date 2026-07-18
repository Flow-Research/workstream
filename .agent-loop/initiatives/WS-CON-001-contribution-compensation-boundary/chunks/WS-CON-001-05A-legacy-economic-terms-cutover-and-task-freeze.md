# Chunk Contract: WS-CON-001-05A - Legacy Economic Terms Cutover And Task Freeze

## Goal

Remove the retired guide-bound economic contract from every semantic consumer,
classify existing rows, and freeze the active published
ContributionPolicyVersion on each successful new TaskAssignment. Physical dead-
schema removal belongs to 05B.

## Risk

L1 economic/task lifecycle/authorization; SLA P1.

## Allowed files

```text
backend/app/modules/contributions/{ports,service}.py
backend/app/modules/projects/{schemas,repository,service}.py only legacy consumer removal
backend/app/modules/tasks/{models,schemas,repository,service}.py only cutover/freeze
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
task-claim permission/grant/kernel implementation
ReviewLease or Review behavior; contribution/award creation
public policy routes; dead physical schema removal
fallback, alias, automatic conversion, or guessed historical rewrite
provider/artifact calls; unrelated checker behavior
```

## Acceptance criteria

- [ ] Every new TaskAssignment has immutable non-null
  `submitter_contribution_policy_version_id`.
- [ ] Exact merged Submission.task_assignment_id lineage is preserved; no
  parallel submission identity is added.
- [ ] No runtime/API/setup/task/checker/review consumer treats retired guide-
  bound terms as current economic authority. A zero-consumer scanner proves
  remaining physical schema is unreachable until 05B.
- [ ] Stable PermissionId `task.claim` exists but no task-claim ActionId is
  registered. AUTH-10 exact same-project submitter ProjectRoleGrant and
  AUTH-PREP contracts are merged; no unrelated project/admin grant substitutes
  and CON contains no role logic.
- [ ] AUTH prepares exact submitter authority first. Task-owned composition
  locks canonical task/assignment facts, invokes the CON participant to lock
  active ContributionPolicy, published version, exact rule/definition/binding
  dependencies and return one same-project version, then recomposes final
  facts. AUTH consumes the handle and evaluates once before TaskAssignment is
  created with that immutable version. CON flushes only and never commits.
- [ ] CON-05A and task-owned claim composition merge while the task-claim
  ActionId remains absent. `WS-AUTH-001-13` enumerates/registers the exact
  action, integrates its evaluator, and activates only after the merged feature
  manifest proves the freeze, canonical guards, rollback, and real-kernel
  unavailable behavior before activation.
- [ ] Missing/invalid policy fails with no assignment/task/audit/outbox partial
  state. Later publication never updates an assignment.
- [ ] Publish versus claim and binding-state versus claim pass both lock orders
  without deadlock or mixed versions.
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
exact assignment freeze and Submission lineage, full rollback on missing or
ambiguous policy, both publication/claim and binding/claim race orders,
real-kernel denial before activation, no runtime legacy-policy consumer,
repository coverage at least 78 percent in the same clean run, and every
focused report at least 90 percent.

## Review and stop

Required tracks: senior, QA, security, product, architecture, docs, reuse, test-
delta, and CI integrity. Stop if exact task/Submission lineage, AUTH-PREP,
task-owned composition seam, or migration classification is not merged. Do not
wait for or perform `task.claim` activation inside this chunk.
