# Chunk Contract: WS-CON-001-04B - Hidden Contribution-Policy Service

## Goal and risk

Implement hidden read/draft/update/publish/retire ContributionPolicy behavior
and canonical resource composition while routes remain absent and AUTH actions
remain planned. L1 economic/auth risk.

## Allowed files

```text
backend/app/modules/contributions/{schemas,repository,service}.py
backend/app/modules/projects/repository.py only policy relationship locking
backend/app/composition/contributions.py
backend/tests/{test_contributions,test_projects,test_authorization,test_api_contract_e2e}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-04B.json
```

## Not allowed

```text
production router registration, task/review claim integration, award results
AUTH catalogue/grant/kernel/static-matrix edits, adapter/provider calls
legacy fallback, dependency or CI weakening
```

## Approved AUTH prerequisites and deferred activation gate

- Before this chunk starts, AUTH must merge reviewed registration of the
  planned `contribution.policy.*` actions, stable permission mapping, typed
  contexts, ActionOwner custody, and PR #140 prepared-mutation ports. The
  actions remain planned. CON does not edit the AUTH catalogue, grants, kernel,
  ActionOwner custody, or static matrix.
- After this hidden feature manifest merges, AUTH alone integrates evaluators
  and activates the actions. CON-05A waits for that activation.

## Acceptance criteria

- [ ] AUTH prepares its exact bound handle first. Publish then locks project,
  active policy, version, rules, definitions, and bindings; recomposes final
  facts; AUTH consumes the handle and evaluates once; only then may the caller
  atomically update current_published_version_id with audit/outbox.
- [ ] Allowed decision evidence matches complete resource digest, grant ID,
  project scope, request, and correlation. Service flushes and never commits.
- [ ] Explicit unpaid is valid. Missing/incomplete/contradictory setup is a
  stable failure. No legacy authority executes.
- [ ] Concurrent draft/publish/retire/selector/binding changes are
  deterministic. Production OpenAPI remains unchanged.
- [ ] The feature manifest is sufficient for later AUTH evaluator integration
  and activation without transferring any AUTH-owned work to CON.

## Verification and reviewers

Execute the exact clean isolated CON-04B row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_projects.py tests/test_authorization.py tests/test_api_contract_e2e.py -k '(policy or publish or retire or binding) and (authorization or rollback or concurrency or idempotency or missing or invalid or openapi)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/contributions app/modules/projects/repository.py app/composition/contributions.py tests/test_contributions.py tests/test_projects.py tests/test_authorization.py tests/test_api_contract_e2e.py)
```

Pass requires a non-empty selected test set, supplied prepared-authorization
ordering, flush-only rollback, deterministic concurrent publication/binding
changes, missing-policy failure, hidden OpenAPI, repository coverage at least
78 percent in the same clean run, and focused contribution coverage at least 90
percent. Required tracks: senior, QA, security, product, architecture, docs,
reuse, and test-delta. Stop after hidden behavior.
