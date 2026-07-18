# Chunk Contract: WS-CON-001-11 - Hidden Release Readiness And Dependency Manifest

## Goal and risk

Prove the core WS-CON subsystem coherent while hidden and publish an exact
merged-SHA/schema/action/service/handler/fence/drain/test manifest for the
reviewed REV release owner. L1 release/auth/economic risk.

## Allowed files

```text
backend/app/composition/{contributions,compensation,outbox}.py
backend/tests/{test_api_contract_e2e,test_authorization,test_contributions,test_compensation,test_outbox}.py
docs/spec_contribution_compensation.md
docs/internal_reviews/WS-CON-001-hidden-release-readiness.md
.agent-loop/initiatives/WS-CON-001-contribution-compensation-boundary/**
.agent-loop/merge-intents/WS-CON-001-11.json
```

## Not allowed

```text
production route registration or noncanonical prefix alias
REV lifecycle-control persistence/policy; AUTH/ART implementation
optional evidence projection/read or ART readiness gate
archival input edits
```

## Acceptance criteria

- [ ] Startup parity covers closed ActionId/PermissionId/ActionOwner, typed
  contexts/evaluators, ServiceIdentity/static rows, and active-feature behavior.
  Active-without-evaluator/behavior or extra/missing matrix membership fails.
- [ ] Missing provisioned service ActorProfile/link rows do not fail app startup
  or Access Administrator provisioning. Protected runtime calls deny and
  release readiness stays false until exact rows exist.
- [ ] AUTH manifest binds trusted baseline, complete REV custody transfer,
  proposed core CON mappings plus separately approved executor actions, D11
  role sets, exact grants/static rows, AUTH-09E admission, prepared protocol,
  decision digests/matched authority, and activation evidence.
- [ ] Prepared-protocol proof binds handles exactly to session, ActionId,
  actor-reference kind/reference, idempotency key, and request digest; proves
  same-session/action cross-actor/request substitution does not mutate state or
  consume a valid handle; and proves ServiceIdentity/matrix/availability are not
  database lock targets.
- [ ] No partial ART/REV transfer is restated. Complete mappings are referenced
  from merged WS-XINT handoffs. ART and optional CON-09A/09B are absent from
  core prerequisites.
- [ ] Hidden integration proves production OpenAPI routes remain absent and no
  direct construction path bypasses AUTH, fixed-service admission, outbox
  handler isolation, or mandatory REV/CON participant composition.
- [ ] Manifest names exact migrations, schemas, event/task IDs, registry rows,
  service identities/actions/static rows, handler execution boundaries, and
  retained test metadata. Dispatcher cannot execute protected handlers.
- [ ] Manifest names mandatory CON obligation-writer, dispatch, callback, and
  same-session `FulfillmentLifecycleDrainObservationPort` hooks plus
  `OutboxClaimValidationPort`, injection seams, phase mappings, denial states,
  and fail-closed construction. REV-12A injects the one shared
  `JointLifecycleMutationFence`; CON defines no second controller or optional/
  no-op fence.
- [ ] The manifest enumerates every fulfillment-obligation root creation,
  requeue, successor, and repair writer and proves each acquires the shared
  fence before allocating its immutable monotonic ordinal or locking obligation
  rows. Missing, extra, ambiguous, differently ordered, or completion-only-
  misclassified writers fail composition and preflight.
- [ ] Drain observation returns pending/claimed/retryable outbox events, durable
  in-flight dispatch, nonterminal delivery/callback obligations, and the current
  maximum root ordinal in the caller session. Independent-session proof races
  every writer against cutoff capture and proves it either commits under an
  included ordinal or observes `commands_draining` without allocation/mutation.
- [ ] Dispatch and callback readiness proves `delivery_draining` permits only
  same-generation, at-or-below-cutoff completion and denies new roots, requeue,
  successor, repair, post-cutoff, and crossed-generation work before provider
  I/O. Disable waits for zero dispatchable/retryable/claimed/in-flight work and
  zero nonterminal delivery/callback obligations.
- [ ] Core conformance matrix has executable evidence; same-run repository
  coverage is at least 78 and changed subsystems at least 90.
- [ ] Joint drill contract covers all core families. Accept proves Task
  `accepted`, Assignment `completed`, one FinalAcceptance and one submitter
  contribution. Needs_revision proves Task `needs_revision`, Assignment still
  `active`, and neither acceptance fact nor submitter contribution. Reject
  proves Task `rejected` with bounded human reason, only the same-task
  Assignment blocked with its source Review, and neither acceptance fact nor
  submitter contribution. Every Review proves one reviewer contribution. It
  explicitly
  asserts zero ART calls and no adjudication model/action/state/queue/readiness
  dependency. It is not marked executed here.

## Verification

Execute the exact clean isolated CON-11 row in `../RUNTIME_VERIFICATION.md`,
then run:

```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_api_contract_e2e.py tests/test_authorization.py tests/test_contributions.py tests/test_compensation.py tests/test_outbox.py tests/test_audit.py -k '(manifest or readiness or openapi or isolation or fence or cutoff or generation or drain or provider)')
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
git diff --check
```

Pass requires a non-empty selected test set, a complete exact AUTH/REV/CON
manifest, no public OpenAPI registration, service/action isolation, every
writer/dispatch/callback fence race in both orders, same-generation
at-or-below-cutoff completion only, provider I/O outside transaction/fence,
repository coverage at least 78 percent and each CON-11 focused subsystem at
least 90 percent in the same clean run, plus every repository gate above.

## Review and stop

All internal tracks including CI integrity and test-delta. Stop after hidden
manifest. Do not register routes, implement REV release control, run production
activation, or start optional evidence work.
