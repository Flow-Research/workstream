# WS-AUTH-001-09A PR Trust Bundle

## Chunk

`WS-AUTH-001-09A` - Fixed Service Identity Foundation

## Goal

Give each internal service ActorProfile one stable ServiceAccount-style local
identity, retain the Identity Issuer subject as a separate credential link, and
define a closed service-action candidate matrix without provisioning or
activating service authority.

## Changes

- Seven fixed service identities and immutable, unique
  `ActorProfile.service_identity` semantics for service profiles only.
- Eight planned AUTH-09 actions with complete PostgreSQL audit parity.
- One exact seven-identity/eleven-action matrix validated against PermissionId,
  historical owner metadata, and planned availability.
- Guarded migration `0023`, a confidential exact-set operator mapping tool, and
  immutable bounded migration evidence.

## Boundary

ActorProfile is the stable local principal. `(issuer, subject)` is only the
credential link. Authority candidates come from reviewed typed code, never
email, token roles, display fields, grants, dynamic assignment rows, or request
input.

This chunk adds no route, provisioning, service admission, evaluator, resource
composer, feature behavior, grant, action activation, compatibility alias,
fallback, or second identity model. Internal services are not human
Contributors.

## Proof

- Catalogue: 74 permissions, 65 actions, nine active, 56 planned.
- Matrix: seven identities, eleven exact memberships, all planned.
- Targeted catalogue/matrix/audit tests: 10 passed.
- Broader focused custody/catalogue tests: 54 passed.
- Isolated PostgreSQL revision `0023` proof: three passed.
- Changed-subsystem branch-aware coverage: 94 percent migration tool, 92
  percent catalogue, 93.41 percent combined.
- Ruff, stale scans, links, merge intent, loop state, 80 agent-gate tests, 91.9
  percent docstring coverage, and diff integrity pass.

Exact implementation SHA
`fe61df64fbf82a1f6871c380e6fc1986a4f12205` passed senior engineering,
QA/test, security/auth, product/ops, architecture, CI integrity, docs,
reuse/dedup, and test-delta review after valid findings were repaired.

## External Review

Earlier CodeRabbit findings on mutable historical migration imports and
cross-event-loop cleanup are fixed. The migration consumes a packaged frozen
contract and the operator lifecycle uses one async loop with explicit error
precedence. Replacement external checks are pending on the converged head.

## Follow-up

PR #140 resolved activation custody: feature owners supply hidden facts, guards,
behavior, and typed manifests; only AUTH integrates evaluators and changes
availability. Implementation remains deliberately separate. The binding order
is `09B -> 09C -> 09D -> 09E -> ART/REV custody -> PREP`, with a human start
required at each chunk boundary.

## Remaining Risk

A host crash during private-envelope publication may require regenerating the
file. Missing, partial, or unverifiable evidence remains fail-closed.

## Human Review Focus

Review the fixed identity model, strict private mapping custody, exact matrix
metadata, inert actions, immutable evidence, and absence of dynamic assignment
or compatibility authority. Only the human may approve and merge this PR.
