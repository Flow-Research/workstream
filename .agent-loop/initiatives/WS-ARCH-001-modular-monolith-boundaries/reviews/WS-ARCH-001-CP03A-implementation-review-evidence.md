# WS-ARCH-001-CP03A Implementation Review Evidence

## Scope reviewed

The complete CP03A implementation: ACTORS-owned closed identity vocabulary and
adapter eligibility, PROJECTS-owned project eligibility, target-only AUTH
matrix handling, migration `0005`, focused PostgreSQL and unit proof, boundary
ledgers, semantic-lane ownership, and canonical state/documentation updates.

## Deterministic evidence

- touched-code Ruff: pass;
- 32 focused ACTORS/PROJECTS/kernel tests: pass;
- 11 focused service identity/matrix tests: pass;
- isolated PostgreSQL migration, real owner-fence, committed-ineligibility,
  identity-link revocation, and controlled provisioning proof: pass;
- canonical semantic-lane collection: pass;
- module-boundary, behavior-ownership, and test-structure gates: pass;
- stale authorization/workstream wording, Markdown links, chunk-state sync,
  and diff checks: pass.

GitHub Actions owns the complete PostgreSQL matrix and repository coverage. The
local machine does not run the full suite.

## Findings fixed

Review found and fixed the migration naming-convention expansion, stale schema
fingerprint, missing semantic-lane assignments, missing referenced-identity
downgrade proof, incomplete real owner-lock evidence, missing controlled target
provisioning proof, missing exact identity-link race proof, stale wording, and
one allowed-file mismatch. No CI threshold, test selection, action availability,
or authorization rule was weakened.

## Internal review disposition

- Architecture: pass with low transitional re-export risk.
- Security/authorization: pass after real profile/link/project fence proof.
- Product/operations: pass; the target is not the Finance Authority caller.
- QA: pass after migration, fingerprint, scope, and PostgreSQL corrections.
- Test delta: pass; no skip, xfail, removal, or assertion weakening.
- CI integrity: pass after semantic-lane reconciliation.
- Senior engineering: pass after stale wording and real-fence correction.
- Reuse/dedup: pass with low intra-PROJECTS query reuse risk.
- Documentation: pass after canonical action-bearing/target-only identity
  wording and state reconciliation.

## Residual risk

`app.modules.actors.service_identities` remains a transitional private
re-export for untouched frozen imports. New and touched consumers must use
`app.modules.actors.api`. CP03B must add the real AUTH read/PREP composition and
activate only the four Finance Authority binding actions; CP03A grants no
action to the adapter target.
