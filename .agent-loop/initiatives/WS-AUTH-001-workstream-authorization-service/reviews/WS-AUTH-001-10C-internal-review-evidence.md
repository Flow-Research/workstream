# Internal Review Evidence: WS-AUTH-001-10C

## Chunk And Reviewed Code

`WS-AUTH-001-10C` — Project Role Grant Mutations. Risk: L1 authorization,
concurrency, migration, and audit integrity. Trusted-main start base is
`bcf1292e1a591e3e84bf8ee212ee7191d80741fa`; signed start run is
`30014637065`.

Reviewed implementation SHA: `2e2969fe712f361ff14b1c90bca439d16777d255`
Reviewed at: 2026-07-24

## Implemented Contract

- Activates covered-Project-Manager issue and revoke actions and their strict
  project-role mutation routes.
- Binds idempotency, PREP, current caller/target/project/grant facts, resource
  context digest, lexical locks, final authorization consume, evidence, and one
  route commit.
- Persists one immutable qualification snapshot before an issued grant; issue
  emits no invalidation. Revoke remains available for every existing project
  lifecycle state and after target lifecycle or identity-link loss.
- Conceals missing, inactive, nonhuman, unauthorized, cross-project, and absent
  resources as the same `404 resource_not_found`, while preserving explicit
  self-grant and self-revoke guards.
- Adds migration `0034_project_role_issue_evidence`, frozen predecessor and
  forward definition hashes, exact trigger and constraint checks, strict
  two-event issue evidence, and actor/grant/role/project/future-obligation
  linkage for revoke invalidation evidence.
- Keeps AUTH-11, assignment, review reconciliation, automated role conversion,
  frontend work, and unrelated schema changes out of scope.

## Deterministic Evidence

```text
Ruff on changed authorization, audit, migration, and test files — passed
git diff --check — passed
Markdown link scan — passed
Authorization stale-wording scan — passed
Route concealment and self-guard matrix — 33 passed
Project lifecycle HTTP/direct-route matrix — 18 passed
Incompatible pending response migration refusal — 1 passed
Privacy definition drift refusal/restoration — 1 passed
Function and disabled-trigger drift refusal/restoration — 2 passed
Revoke linkage malformed/valid PostgreSQL evidence — 1 passed
Five-key revoke downgrade refusal/no-mutation — passed
```

The PostgreSQL proof uses the repository-owned isolated database runner. It
covers frozen function/trigger/constraint drift, pending incompatible state,
false issue invalidation, strict five-key revoke facts, null/wrong/orphan/mixed/
cross-record linkage, exact teardown, and downgrade refusal without mutation.

The repository-wide suite and coverage remain GitHub Actions-owned because the
local full run takes approximately four hours. Required GitHub gates retain the
repository-wide 78 percent floor and authorization-subsystem 90 percent floor.

## Integrity And Review

No test was deleted, skipped, xfailed, or weakened. No workflow, dependency,
shard, command, threshold, package script, or coverage configuration changed.
Migration `0034` is tracked and follows `0033_authorization_read_rate`.

| Reviewer | Result | Blocking findings |
|---|---|---|
| Senior engineering | PASS | none |
| Architecture | PASS | none |
| Reuse/dedup | PASS with low risks | none |
| Security/auth | PASS | none |
| QA/test | PASS with low risks | none |
| Test delta | PASS | none |
| Product/ops | PASS | none |
| Docs | PASS | none |
| CI integrity | PASS | none |

The repair loop closed migration fixture restoration, frozen definition drift,
decision substitution, route concealment and zero-mutation, project lifecycle,
revoke target linkage, non-revoke five-key evidence, and downgrade proof gaps.

Open sub-agent sessions: none
Valid findings addressed: yes
