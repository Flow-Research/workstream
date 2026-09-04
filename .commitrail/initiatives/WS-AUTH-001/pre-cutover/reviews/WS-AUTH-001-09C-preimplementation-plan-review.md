# WS-AUTH-001-09C Preimplementation Plan Review

## Scope

Privacy-bounded administrative reads for one exact ActorProfile and its single
v0.1 ActorIdentityLink. No list, mutation, project-scoped actor-registry
authority, service admission, or feature action activation is in scope.

## Initial candidate

- SHA: `9ea44c0a07b16126a6feed46e785ee5359baf680`
- Result: **FAIL**
- Runtime edits at review: none

## Required repairs

| Reviewer group | Required repair |
|---|---|
| security/auth and product/ops | Include exact audit parity and expose the closed local `service_identity` for service lifecycle targeting without external identity or matrix disclosure. |
| architecture/concurrency and reuse | Revalidate and lock caller profile, exact link, and matched grant through disclosure; enforce action-specific resource classes; reuse ActorService and ActorRepository target reads. |
| QA/CI and integration | Allow and run `test_audit.py`; require two-decimal 90 percent thresholds; add deterministic two-session race and strict API proof. |

## Final candidate

- SHA: `76c5427c5dedc0716d38c3fb1f9b1e45df8cdc8e`
- Result: **PASS**
- Runtime edits at review: none

| Reviewer group | Result | Open finding |
|---|---|---|
| security/auth, roles, privacy, and product/ops | PASS | none |
| architecture, concurrency, service boundary, and reuse | PASS | none |
| QA/test, CI integrity, API contract, REV/CON isolation | PASS | none |

The exact candidate also passed stale wording, authorization-doc consistency,
Markdown links, all agent-gate tests, and diff integrity. Runtime implementation
may proceed only within this reviewed AUTH-09C contract.
