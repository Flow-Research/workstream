# Chunk Contract: WS-CON-001-08B - Inbound Fulfillment Callback

## Goal and risk

Accept authenticated bound-service fulfillment results and create immutable
receipts/status updates. L1 auth/economic/replay risk.

## Allowed files

```text
backend/app/modules/compensation/{schemas,repository,service,ports}.py
backend/app/api/internal_compensation.py
backend/app/composition/compensation.py
backend/tests/{test_compensation,test_authorization,test_api_controls,test_api_rate_controls,test_api_contract_e2e}.py
docs/spec_contribution_compensation.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-08B.json
```

## Not allowed

```text
AUTH catalogue/grant/ServiceIdentity/static-matrix implementation edits
human role fallback; dynamic service grant; provider credentials
outbox transition ownership; production route registration
```

## Acceptance criteria

- [ ] Human/AUTH approves exact callback ServiceIdentity and static
  `compensation.fulfillment.report` row (or an explicitly closed set of
  identities), provisions ActorProfile/link, admits through AUTH-09E, and keeps
  the action planned until hidden callback behavior merges.
- [ ] Prepared callback locks profile/link and validates immutable
  ServiceIdentity, matrix membership and active action as code-owned facts.
  AUTH prepares its exact bound handle; CON locks binding/award/delivery/
  receipt rows and recomposes final facts; AUTH consumes/evaluates once before
  callback mutation.
- [ ] Exact route identity, project, instrument, award, frozen binding, external
  event, quantity/status, and idempotency must match. Actor/link/binding state
  loss denies.
- [ ] After CON-owned signature verification plus AUTH/idempotency locking, the
  callback acquires the shared `JointLifecycleMutationFence`, resolves the
  canonical obligation root, immutable ordinal, and generation, and holds the
  fence through receipt commit. In `delivery_draining`, only same-generation
  roots at or below the persisted cutoff may finalize; `disabled`, post-cutoff,
  crossed-generation, or missing lineage denies before provider/follow-on I/O.
- [ ] Callback finalization cannot create a successor event, retry root,
  delivery obligation, repair, award, or other follow-on work while draining.
  Callback-versus-disable tests prove the exclusive transition cannot cross an
  in-flight receipt transaction.
- [ ] Duplicate exact receipt is idempotent; changed replay conflicts; fulfilled
  receipt is immutable and at most one exists per award.
- [ ] Suspended binding accepts only valid already-issued obligations; retired
  binding accepts only exact replay of a receipt accepted before retirement.
- [ ] Callback-before-local-ack creates terminal truth and suppresses later
  delivery without regression. Both lock orders and rate limits per actor plus
  binding are covered.
- [ ] Missing provisioned callback rows deny callback/readiness but do not fail
  startup/provisioning. AUTH later activates after hidden behavior proof.

## Verification

Execute the exact clean isolated CON-08B row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_compensation.py tests/test_authorization.py tests/test_api_controls.py tests/test_api_rate_controls.py tests/test_api_contract_e2e.py -k '(callback or receipt or fulfillment) and (replay or conflict or fence or cutoff or generation or rate or authorization or signature or concurrency or openapi)')
(cd backend && .venv/bin/python -m coverage report --include='app/modules/compensation/*' --fail-under=90)
(cd backend && .venv/bin/ruff check app/modules/compensation app/api/internal_compensation.py app/composition/compensation.py tests/test_compensation.py tests/test_authorization.py tests/test_api_controls.py tests/test_api_rate_controls.py tests/test_api_contract_e2e.py)
```

Pass requires a non-empty selected test set, exact callback replay and changed
replay conflict, signature and authorization negatives, actor-plus-binding rate
isolation, both fence race orders, same-generation at-or-below-cutoff
finalization only, no follow-on obligation while draining, repository coverage
at least 78 percent in the same clean run, and focused compensation coverage at
least 90 percent.

## Review and stop

All baseline plus architecture, security, product, docs, reuse, test-delta, and
CI integrity. Stop before public registration.
