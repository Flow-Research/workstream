# Chunk Contract: WS-CON-001-10A - Contribution And Award Product Reads

## Goal and risk

Implement hidden authorized self/project reads directly from canonical
PostgreSQL ContributionRecord and CompensationAward truth. L1 auth/privacy risk.

## Allowed files

```text
backend/app/modules/contributions/{schemas,repository,service}.py
backend/app/modules/compensation/{schemas,repository,service}.py
backend/app/api/internal_{contributions,compensation}.py
backend/app/composition/{contributions,compensation}.py
backend/tests/{test_contributions,test_compensation,test_authorization,test_api_contract_e2e}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-10A.json
```

## Not allowed

```text
ART/evidence read or provider reference
operations mutation/rebuild/reconciliation; AUTH edit
balance/ledger; production route registration; CI weakening
```

## Approved AUTH prerequisites and handoff inputs

- AUTH must first merge the approved contribution/award self/project
  ActionIds, typed contexts, ActionOwner custody, and real-kernel decision
  ports. CON neither registers nor activates them.
- The actions remain planned until CON's hidden read composition and negative
  proof merge; AUTH alone performs later evaluator integration and activation.

## Acceptance criteria

- [ ] CON composes canonical PostgreSQL resource facts for the supplied AUTH
  decision ports while the real kernel continues to deny planned actions.
- [ ] D11 exact award-detail candidate set is approved before implementation.
  CON contains no role logic and never infers access from broad PermissionId.
- [ ] Self reads require exact contributor/beneficiary. Project reads use exact
  eligible AdminRole, covered project, pre-filtered stable pagination, and
  cross-project concealment. Reviewer has no project-wide access by review role.
- [ ] Allowed decisions bind complete resource digest, matched grant/project,
  request, and correlation. Stale/mismatched evidence denies.
- [ ] Contribution, money, points, delivery acknowledgement, and fulfillment
  are distinct. No provider/balance/ledger/evidence artifact data appears.
- [ ] CON-09A/09B absence or failure has no effect. OpenAPI remains hidden;
  coverage stays at required floors.

## Verification

Execute the exact clean isolated CON-10A row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_api_contract_e2e.py -k '(contribution or award) and (read or list or pagination or conceal or cross_project or unauthorized or stale or openapi)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/contributions/*' --fail-under=90)
(cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/contributions app/modules/compensation app/api/internal_contributions.py app/api/internal_compensation.py app/composition/contributions.py app/composition/compensation.py tests/test_contributions.py tests/test_compensation.py tests/test_authorization.py tests/test_api_contract_e2e.py)
```

Pass requires a non-empty selected test set, stable pre-filtered pagination,
self/project authorization negatives, cross-project concealment, stale-decision
denial, hidden OpenAPI routes, no evidence/provider disclosure, repository
coverage at least 78 percent in the same clean run, and both focused reports at
least 90 percent.

## Review and stop

Required tracks: senior, QA, security, product, architecture, docs, reuse, and
test-delta. Stop before operations/public registration.
