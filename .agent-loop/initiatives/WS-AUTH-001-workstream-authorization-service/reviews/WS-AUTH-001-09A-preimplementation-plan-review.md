# WS-AUTH-001-09A Preimplementation Plan Review

## Verdict

`PASS`

The original contract passed at
`b44ef8ae1e1b4532d7af9477d688113057ff34cb`. That approval was historical after
PR #140 merged the binding XINT reconciliation. The converged contract and
implementation received fresh exact-head review at
`fe61df64fbf82a1f6871c380e6fc1986a4f12205`.

The contract-only addendum at
`5ba7bf7e781061f1bc23fb36973ed95ce563ac42` added the existing
`backend/tests/test_auth.py` service-profile regression fixture to allowed
files and verification. The same composite senior/architecture/CI/docs/reuse,
QA/product/test-delta, and security/auth tracks passed that exact addendum; no
runtime behavior or implementation direction changed.

## Review results

| Track | Result | Notes |
|---|---|---|
| senior engineering | PASS | Scope is one reviewable identity/catalogue/migration foundation with no runtime surface. |
| QA/test | PASS | Exact counts, zero/subset/all-seven mapping behavior, independent coverage gates, downgrade, and no-runtime-delta proof are testable. |
| security/auth | PASS | Stable local principal, opaque credential link, private exact-set mapping, bounded evidence, no grants/assignment rows, and planned inertness are explicit. |
| product/ops | PASS | Service actors remain internal and cannot become Contributor, admin, or project-role actors. |
| architecture | PASS | ActorProfile owns fixed identity; AUTH owns the static candidate policy and all later evaluator integration/activation. Feature owners supply hidden facts, guards, behavior, and typed manifests. |
| CI integrity | PASS | No workflow, dependency, skip, exclusion, or threshold change is allowed. |
| docs | PASS | Canonical spec, runbook custody, route families, counts, and stop paths are synchronized. |
| reuse/dedup | PASS | One identity registry and one static matrix replace duplicate persisted assignments. |
| test delta | PASS | Required behavior and migration suites are additive; existing nine active actions and OpenAPI remain unchanged. |

## Approved implementation boundary

- Add one fixed service identity enum/field and migration `0023`.
- Add eight planned AUTH-09 route actions and exact audit mapping parity.
- Add one static seven-identity/eleven-ActionId candidate matrix.
- Support confidential exact mapping for preexisting `0020` service profiles.
- Update existing auth regression fixtures that construct a service profile so
  they satisfy the new fixed identity invariant; no authentication behavior
  changes.
- Persist only bounded migration evidence.
- Do not add routes, provision actors, admit service tokens, activate AUTH-09 or
  artifact actions, create assignment tables, or create service grants.

Runtime implementation may begin. AUTH-09B remains inactive.

The binding successor sequence is `09A -> 09B -> 09C -> 09D -> 09E`, followed
by availability-neutral ART/REV custody transfer and PREP. No successor starts
without merge memory and a separate human start signal.
