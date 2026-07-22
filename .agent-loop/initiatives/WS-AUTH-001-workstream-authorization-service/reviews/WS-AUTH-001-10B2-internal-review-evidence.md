# Internal Review Evidence: WS-AUTH-001-10B2

## Chunk And Reviewed Code

`WS-AUTH-001-10B2` — Privacy-Safe Project Role Grant Reads. Risk: L1
authorization/privacy. Trusted main is `14fa4316f7d984f2176657bfafd2a2dae56f944e`.

Reviewed code SHA: `f00759f0242752150d2c7e8b3ea17f1f486678ea`
Reviewed at: 2026-07-22T05:17:30Z
Reviewer run IDs: /root/auth10b1_final_core, /root/auth10b1_final_security_qa, /root/auth10b1_final_ops_docs_ci

Runtime repair SHA `95c3ecf77afed2746a66f314d05eb547cfa15f3c`
was reviewed by the same tracks before the evidence-only descendants.

## Implemented Contract

- Activates exactly three AUTH-10B project candidate/grant read actions/routes;
  AUTH-10C remains planned.
- Orders one durable rate consumption, nonhuman concealment, project load,
  kernel authorization, cursor validation, then private row SQL.
- Adds strict count-free responses and HMAC-SHA256 keysets bound to normalized
  action, project, filters, limit, order, timestamp, and UUID.
- Requires an independent canonical Base64 32-byte startup key with no default,
  fallback, serialization, or authentication/rate-key reuse.
- Adds no migration and changes no PREP, issue, revoke, or mutation behavior.

## Deterministic Evidence

```text
148 passed — complete configuration test file
42 passed, 218 deselected — cursor/rate/nonhuman/kernel/read-service row
1 passed — exact OpenAPI inventory and protected-action manifest
2 passed — OpenAPI plus one-link structural candidate constraint
2 passed in 53.82s — isolated PostgreSQL candidate/grant keysets, filters,
service exclusion, project binding, limit+1, and no-COUNT SQL
Ruff app/tests/scripts — passed
Python compileall app/hosted drill — passed
Docstring coverage — 87.6% against 80% floor
Markdown links and stale wording/authorization scans — passed
git diff --check — passed
```

The repository-wide suite is GitHub-owned because this workstation previously
required about four hours and a broader local run hit SQLAlchemy process
instability. GitHub must prove all shards, hosted API E2E, the 78% repository
floor, and the 90% authorization-subsystem floor.

## Integrity And Review

No test was deleted, skipped, xfailed, or weakened. Exact OpenAPI inventory is
strengthened from 62 to 65 routes and 60 to 63 protected operations. No
workflow, dependency, command, shard, threshold, or coverage setting changed.

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

Exact-SHA reviewers: `/root/auth10b1_final_core`,
`/root/auth10b1_final_security_qa`, and `/root/auth10b1_final_ops_docs_ci`.
Two repair cycles closed every valid finding. Open reviewer sessions: none.

Open sub-agent sessions: none
Valid findings addressed: yes

## Internal Repair Re-review

All nine internal tracks pass repair SHA
`95c3ecf77afed2746a66f314d05eb547cfa15f3c` with no open finding. External
GitHub and CodeRabbit findings, repairs, and final statuses are recorded only in
`WS-AUTH-001-10B2-external-review-response.md`.
