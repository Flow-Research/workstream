# Internal Review Evidence: WS-AUTH-001-10C

## Chunk And Reviewed Code

`WS-AUTH-001-10C` — Project Role Grant Mutations. Risk: L1 authorization,
concurrency, and audit. Trusted-main start base is
`bcf1292e1a591e3e84bf8ee212ee7191d80741fa`; signed start run is
`30014637065`.

Reviewed code SHA: `0d05b7096eb7a2cf7c68a1770c0b35f07d5b55df`
Reviewed at: 2026-07-23T16:55:00+01:00
Reviewer run IDs: /root/auth10b1_final_core, /root/auth10b1_final_security_qa, /root/auth10b1_final_ops_docs_ci

## Implemented Contract

- Activates exactly the covered-Project-Manager issue and revoke actions and
  their two strict `/api/v1/projects/.../role-grants` mutation routes.
- Binds idempotency, PREP, current caller/target/project/grant facts, lexical
  principal locks, deterministic absence serialization, and one route commit.
- Persists one immutable qualification snapshot per issued exact role; revoke
  remains possible after target suspension or identity-link revocation.
- Appends ordered typed success evidence and the revoke-only future-obligation
  invalidation projection through the shared authority mutation completion path.
- Adds no migration, schema revision, worker, assignment, review-reconciliation,
  automated grant, replacement-role, or authority-substitution behavior.

## Deterministic Evidence

```text
Focused project-role schema/advisory/rate/invalidation/cancellation tests — passed
Crossed-principal lexical profile/link order in both directions — passed
Python compile of authorization tests — passed
Ruff on changed authorization tests and implementation — passed
git diff --check — passed
Markdown links and stale wording scans — passed
```

The PostgreSQL proof covers durable issue/revoke evidence, revocation after
target lifecycle loss, the real named partial-unique-index fallback through the
public route, loser residue, observed database lock waiting, production
cancellation rollback, and a completed same-key retry. It runs in GitHub with
the repository database fixture. The repository-wide suite and coverage remain
GitHub-owned because this workstation's full run takes approximately four hours.

## Integrity And Review

No test was deleted, skipped, xfailed, or weakened. The exact OpenAPI inventory
is 76 routes with hash
`c8f9852035446ea59b0e929b1bd8c8cfc7df5bf838ceb544c04e899f90169318`
and 74 protected operations with hash
`9278d0183ffb87947ee4857e0325483ba7bf07feac0c38a88432840b10c2b0c3`.
No workflow, dependency, shard, command, threshold, or coverage setting changed.

| Reviewer | Result | Blocking findings |
|---|---|---|
| Senior engineering | PASS | none |
| Architecture | PASS | none |
| Reuse/dedup | PASS | none |
| Security/auth | PASS | none |
| QA/test | PASS | none |
| Test delta | PASS | none |
| Product/ops | PASS | none |
| Docs | PASS | none |
| CI integrity | PASS | none |

The repair loop closed lifecycle attribution, real unique-index fallback,
complete residue, database-observed cancellation, committed retry, and lexical
crossed-principal proof gaps. Open reviewer and sub-agent sessions: none.

