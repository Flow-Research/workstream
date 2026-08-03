# WS-AUTH-001-12E PR Trust Bundle

## Intent

Activate exactly the three guide-sufficiency mutations: manual report create,
agent run, and warning acknowledgement. Public mutation remains Project
Manager-only; the fixed `workstream.project.setup` service may execute only the
internal run command with exact setup custody.

## Design and scope

- All durable mutations use the existing opaque, process-local,
  transaction-bound `PreparedAuthorizationHandle` protocol.
- Decisions bind actor/link, grant or fixed service, action, project, draft
  guide/version, source snapshot/hash, setup run/generation, material digest,
  operation, request digest, idempotency key, session, and root transaction.
- PostgreSQL migration 0050 adds immutable replay and complete create/acknowledge
  authorization provenance without rewriting historical rows.
- External agent work occurs outside a prepared handle. Final authority and
  canonical lineage are reacquired before persistence.
- Replay reservation, report or acknowledgement, allowed decision evidence,
  and replay completion commit atomically.
- The active Celery worker reloads fixed-service authority at execution time.
  Handles, bytes, extracted content, credentials, and authorization context do
  not enter Celery payloads.

## Critical safety proof

- Fixed-service tokens are concealed at public admission before product lookup.
- Wrong actor/link/action/resource/session/transaction, copied or replayed
  handles, stale lineage/material/output, and cross-action keys fail closed.
- Deterministic Celery task identity is stored before enqueue and rebound at
  worker admission and setup custody.
- Terminal runs and wrong-task deliveries cannot be revived.
- A setup run made terminal in a competing transaction during agent execution
  is rejected under the final lock with no report or output attachment.
- A fault after final PREP and replay staging rolls back the protected product
  row, replay row, and allowed audit evidence together.

## Local evidence

- Ruff over backend application, tests, and scripts: passed.
- Project sufficiency selector: 31 passed.
- Authorization prepared/catalogue/service selector: 144 passed.
- Migration 0050 upgrade/downgrade selector: 2 passed.
- Mid-flight terminal race: 1 passed.
- Real API contract E2E: passed.
- Semantic lane collection: 2,928 tests assigned across five lanes.
- Stale authorization docs, stale Workstream wording, Markdown links, and seven
  lightweight agent-gate tests: passed.
- Diff whitespace check: passed.
- External-review correction selectors for OpenAPI/action parity,
  authorization boundaries, ART fixed-service composition, and canonical
  schema/reset custody: passed.

The repository-wide suite and the authoritative per-file 90 percent coverage
gate intentionally run in hosted GitHub Actions; the user's machine is not used
for the roughly four-hour local full suite.

## Internal review

Security, product/operations, QA, senior engineering, architecture, test delta,
CI integrity, documentation, and reuse/dedup reviews passed. Architecture and
test-delta reviewers recorded only non-blocking future-maintenance risks.

## Human review focus

- Confirm only the three intended catalogue actions become active.
- Inspect migration 0050 replay/provenance constraints and downgrade refusal.
- Inspect the external-agent transaction break and final locked revalidation.
- Inspect fixed-service task identity, terminal-state fencing, and the absence
  of service authority on public routes.

## Remaining gate

The initial hosted run exposed stale cross-suite fixtures and one missing test
reset guard; those failures and all actionable CodeRabbit findings have been
corrected without weakening CI. The next exact pushed SHA must pass GitHub
`Backend / test`, `Agent Gates`, the full
78 percent repository baseline, AUTH subsystem coverage, the two new per-file
90 percent coverage checks, and CodeRabbit. No merge is authorized by this
bundle.
