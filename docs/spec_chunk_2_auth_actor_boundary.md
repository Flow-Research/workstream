# Historical Chunk 2 Auth And Actor Boundary

## Status

Implemented historical record, superseded for target authorization semantics by
ADR 0012 and `docs/spec_authorization_service.md`.

## Original Scope

Chunk 2 established the FastAPI boundary that verifies an externally issued
Flow token without Workstream owning login, signup, password reset, password
storage, or primary sessions.

It introduced:

- the `AuthVerifier` interface;
- production and local-development adapter boundaries;
- the current-actor FastAPI dependency;
- stable issuer/subject-derived local attribution;
- development-verifier fail-closed environment controls;
- `GET /api/v1/auth/me` as a protected verification smoke endpoint.

No database actor/grant model or Workstream login behavior belonged to that
chunk.

## Superseded Authorization Semantics

The historical response/context included observed role and claim data because
the original runtime used it during bootstrap. Those values remain legacy
compatibility/audit evidence only. They do not define the target verified-token
type and cannot authorize a migrated product surface.

WS-AUTH-001 evolves the existing verifier boundary rather than replacing it:

```text
AuthVerifier
-> VerifiedIssuerToken (identity and coarse scope only)
-> ActorResolver
-> ActorProfile + ActorIdentityLink
-> AuthorizationContext
-> Workstream-owned grants, permissions, resources, and lifecycle guards
```

The `/api/v1` namespace remains canonical. Workstream still owns no login,
password, token issuance, or primary session.

## Historical Proof Retained

The original implementation proved:

- missing/invalid bearer tokens are rejected;
- local development verification cannot run in production;
- actor attribution is based on issuer/subject rather than email;
- routers do not own product policy;
- no local password/session routes exist.

Later WS-AUTH-001 chunks must preserve those assertions while adding production
issuer/JWKS verification, canonical actor resolution, local grant authority,
negative token-role proof, revocation, and append-only authority evidence.
