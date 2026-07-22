# PR Trust Bundle: WS-AUTH-001-10B2

## Chunk And Goal

`WS-AUTH-001-10B2` exposes privacy-safe contributor candidates and immutable
project-role grant history through three exact authenticated, rate-controlled
read actions. Risk is L1 authorization/privacy.

## Human-Approved Intent

The user explicitly started this signed successor after 10B1 merged and requires
end-to-end safety before 10C. Signed loop memory binds it to main `14fa4316`.

## Change, Design, And Scope

- Added signed keyset cursors and a required independent startup secret.
- Added candidate and grant-history repository reads with exact filters,
  project binding, `limit + 1`, no count, and timestamp/UUID progression.
- Added typed contexts, kernel guard, action-aware concealment, minimal schemas,
  and exactly three `/api/v1/projects/...` GET routes.
- Strengthened PostgreSQL, OpenAPI, config, focused, and hosted API proof.
- Documented provisioning, rotation, disclosure, authority, state, and errors.
- Added one merge intent naming 10C as an explicit-start successor.

Authorization precedes cursor/row lookup. Candidate lifecycle remains inside the
kernel; grant history remains readable in every project state. All verified
nonhumans are rate-gated then concealed before actor/product SQL. Sensitive
absence and denials share one 404.

All files are contract-allowed. There is no migration, workflow/dependency edit,
PREP change, mutation activation, frontend work, or AUTH-10C surface. Responses
never expose totals, identity-link facts, issuer/subject, contact, claims, or keys.

## Proof And Review

Focused evidence passes: 148 config tests; 42 cursor/rate/kernel/service tests;
exact OpenAPI inventory; and two isolated PostgreSQL candidate/grant tests.
Ruff, compileall, docstrings, links, stale scans, and diff hygiene pass. Hosted
E2E provisions a cursor key and checks all routes, strict nonempty nested shapes,
stable concealment, exact actions, and 10C/context absence.

No test or CI threshold was weakened. All nine internal tracks pass exact SHA
`95c3ecf77afed2746a66f314d05eb547cfa15f3c` with no open finding.

## External Review, Risk, And Human Focus

GitHub full shards/API E2E/coverage, Agent Gates, and CodeRabbit remain required.
The first hosted run exposed missing project-scoped reader authority and one
stale exact audit action set. Repair SHA `95c3ecf7` provisions a distinct reader
through the public project-scoped AdminRoleGrant API and adds only the three
activated actions to audit parity; all internal tracks pass the repair.
Human review should focus on ordering, PM/Audit scope and lifecycle boundaries,
cursor binding, response minimization, identical concealment, and the exact
three-action activation. The user retains merge ownership; do not merge without
explicit approval of the specific PR.
