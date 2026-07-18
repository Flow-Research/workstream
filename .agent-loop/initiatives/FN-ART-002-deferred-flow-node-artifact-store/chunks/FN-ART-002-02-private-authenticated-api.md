# Chunk Contract: FN-ART-002-02 Private Authenticated API

Initiative: `FN-ART-002` | Risk: L1 | Status: Deferred

## Goal

Expose ArtifactStore v2-equivalent private service routes with fixed Workstream
service authentication, TLS, quotas, and redaction.

## Allowed Files

- focused Flow Node private API and auth middleware
- service identity/TLS/limit configuration
- bounded provider DTOs and stable errors
- focused security and real HTTP integration tests
- operations and rotation docs

## Not Allowed

- human bearer-token acceptance or product roles;
- public routes, product authorization, search, delete, or retain/release;
- Workstream code or credentials committed to either repository;
- forwarding request-user identity as provider execution authority.

## Acceptance Criteria

- pinned issuer, audience, asymmetric algorithms, time, nonce/JTI, and exact
  scope validation applies to every byte route.
- only a pre-provisioned Workstream service subject is accepted.
- human and unrelated service subjects are denied.
- TLS is required and credentials rotate without product-schema changes.
- errors/logs never retain tokens, keys, raw bytes, or internal paths.
- put/observe-put-result/open/range/head semantics are deterministic and
  bounded; observe-put-result is read-only and cannot recover, replay, or
  mutate a write.

## Verification

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets
<focused private API integration command>
```

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

Can Flow Node act only as Workstream's private byte provider?
