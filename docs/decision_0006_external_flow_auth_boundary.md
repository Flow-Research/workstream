# ADR 0006: Workstream Verifies External Flow Auth

## Status

Accepted

## Context

Workstream needs trusted actor context for project setup, task work, review,
audit, contribution records, compensation operations, and reputation signals.

It does not need to become Flow's primary authentication product.

Owning login flows would add password, session, reset, and account-security scope that distracts from the evaluation loop.

## Decision

Workstream verifies external Flow-issued authentication tokens through an auth interface.

Workstream does not implement or own:

- login
- signup
- password reset
- password storage
- primary auth sessions

Actor identity is derived from stable external issuer and subject claims. Email and display name are profile metadata, not primary identity.

Local development may use a development verifier only in explicitly allowed local/test environments, and it must fail closed outside those environments.

## Consequences

Positive:

- Workstream keeps auth scope narrow
- audit records can bind actions to stable Flow identity claims
- production auth can be swapped behind the verifier interface
- weak local development auth cannot silently become production auth

Tradeoff:

- production deployment depends on a configured Flow token verifier
- local actor simulation must remain clearly separated from production auth
