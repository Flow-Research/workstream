# PR Trust Bundle: WS-AUTH-001-11C1

## Chunk

`WS-AUTH-001-11C1` - Project Setup Diagnostic Read Cutover (L1/P1).

## Goal And Human-Approved Intent

Hard-cut exactly six project-guide diagnostic GET routes from issuer role
claims to scoped local administrative grants, without a migration, mutation
change, compatibility path, or 11C2 activation. The user started this chunk on
2026-07-28 after AUTH-11B merged.

## What Changed And Why

- Activated the six contract-owned ActionIds and preserved all three 11C2
  actions as planned.
- Added one project-side diagnostic composer used by all six routes.
- Added strict action/target-kind, project, guide/version, child/collection,
  source-snapshot, and binding-digest authorization facts.
- Locked canonical project, guide, selected diagnostic rows, post-submit
  policy, current actor/identity link, and matched grant through projection and
  commit.
- Deleted the six obsolete service entry points that accepted `ActorContext`
  and performed legacy role checks.
- Added centralized concealed denial, OpenAPI action declarations, persisted
  decision-context digest evidence, docs, tests, and an additive hosted 90%
  branch-coverage gate for the new composer.

## Design Chosen

`ProjectRepository` remains the only project persistence owner. A narrow
application composer loads and locks feature facts, AUTH evaluates one strict
resource context, and authorization-neutral response projection follows in the
same transaction. Historical diagnostic rows remain readable only when their
complete guide-version and source-snapshot binding is canonical.

Rejected alternatives: retaining token-role fallback, duplicating six route
flows, adding an AUTH project repository, using an unbound project-only
context, or weakening the broad legacy project coverage boundary.

## Scope And Product Behavior

Allowed: covered Project Manager, scoped Audit Authority, and system Operator.
Denied with concealed 404: Finance Authority, Access Administrator,
contributors, wrong project scope, revoked grant/link, inactive actor,
non-human caller, missing/cross-project/cross-guide/stale child, and target-kind
mismatch. Authentication and rate controls retain canonical 401/503 and
429/503 responses before private lookup. Read permission grants no mutation
authority.

## Acceptance Evidence And Test Delta

- Six route/action OpenAPI declarations and closed-catalogue counts.
- Kernel allow/deny, target-kind, revalidation, and persisted digest evidence.
- Six-action composer unit matrix, missing/cross-binding failures, and locked
  post-submit policy binding.
- Live database proof for all six routes, cross-project/cross-guide child
  concealment, Project Manager/Operator/Audit allow, Finance/Access
  Administrator/contributor/wrong-scope/revoked denial.
- Admission-order proof for 429, 503, 401, and verified non-human 404 before
  project lookup.
- No tests removed, skipped, or weakened; legacy role checks remain only on
  the non-11C1 mutation routes.

## Checks Run

- Ruff over `app`, `tests`, and `scripts`: pass.
- Focused API controls and authorization tests: 28 pass on final repaired code.
- Admission/API controls focused set: 48 pass.
- Six-action composer branch coverage: 94.68% (required 90%).
- Three focused live PostgreSQL route flows: 3 pass in 117.91 seconds.
- Agent Gates: 6 pass.
- Stale Workstream wording: pass.
- Stale authorization docs: pass.
- Markdown links: pass.
- `git diff --cached --check`: pass.
- Local API E2E attempt: not a pass; the slow local machine timed out reading
  `/openapi.json` after both health probes passed. Hosted API E2E and the full
  suite remain mandatory on the exact PR head.

## CI Integrity

No gate was weakened. Hosted Backend retains semantic lanes, API E2E, global
78%, authorization 90%, and all existing subsystem gates. The new composer
uses a separate coverage data file and a branch-aware 90% focused gate, so it
does not erase or replace combined full-suite coverage.

## Reviewer Results

Preimplementation architecture, security, product/ops, QA, CI-integrity, and
senior-engineering reviews passed after contract repair. Exact implementation
architecture, security, product/ops, senior-engineering, CI-integrity, docs,
reuse/dedup, and test-delta reviews pass. QA passes with the condition that
hosted Backend/API E2E evidence be recorded before completion.

The CodeRabbit correction received focused architecture and security passes;
QA and test-delta passed with only the low residual risk that the 100-row cap is
proved at compiled-SQL rather than a 101-row live route fixture. Exact SQL shape,
ordering, lock target, and cap are asserted, and hosted PostgreSQL lanes remain
mandatory.

## External Review And Remaining Risk

The first hosted Backend run found two stale explicit active-action test
expectations; both were corrected without weakening exact equality. CodeRabbit's
valid findings were addressed with canonical snapshot validation, bounded
newest-first collection locks, setup-run type narrowing, an explicit fixture
bootstrap helper, repository formatting, and corrected contract wording. The
invariant-failure and authority-serialization suggestions were rejected because
they would hide a kernel defect or weaken the approved concurrent-revocation
boundary. Full rationale is recorded in the 11C1 external-review response.
Final-head Backend, Agent Gates, and CodeRabbit evidence remains mandatory.

The next hosted run passed semantic lanes, migrations, health/OpenAPI/auth
probes, project creation, and the authorization-context request, then found one
stale real-API E2E expected action list. That exact list was updated with the six
11C1 actions; production behavior required no correction.

The following hosted run advanced through that assertion and correctly denied
the policy-bundle helper's issuer-role-only token on a migrated diagnostic GET.
The E2E helper now uses its separately provisioned local Project Manager token
for the four 11C1 diagnostic reads while retaining the legacy manager token only
for not-yet-migrated setup mutations.

## Follow-Up And Human Review Focus

AUTH-11C2 remains separate and unstarted. Review the canonical snapshot joins,
post-submit policy binding, concealed response boundary, role matrix, and the
additive coverage step. The human owns merge approval; the agent must not merge
this PR without explicit approval for that PR.
