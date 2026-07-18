# WS-AUTH-001-07B Internal Review Evidence

Reviewed code SHA: `da0230c23467d3b5d639716bce688eb43cbad0ff`
Reviewed implementation SHA: `aabc0f4c0131c53600750258a0bec8be404c7b90`
Reviewed at: `2026-07-15T18:54:30Z`
Reviewer run IDs: auth07b-ci-repair-senior-ci-docs,
auth07b-ci-repair-qa-product, auth07b-ci-repair-security-arch
Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## Deterministic Evidence

- The focused authorization, auth, actor, API-control, and application suite
  passed 210 behavior tests against fresh isolated PostgreSQL.
- The complete audit suite passed all 12 tests after reconciling its exhaustive
  action-availability matrix with the two newly active actor-self actions.
- Branch-aware focused coverage is 94.65 percent, above the required 90 percent
  threshold. The authorization kernel and runtime each report 100 percent.
- Real API E2E passed from migration base through head and exercised signed
  issuer-token actor self GET/PATCH through the canonical dependency.
- Deterministic behavior tests cover suspended read/update separation, revoked
  and deactivated denial, rollback then unchanged denial evidence, request-local
  state, and the synchronized revoke-versus-update outcome without sleeps.
- The action inventory keeps only `actor.profile.read_self` and
  `actor.profile.update_self` active. Unknown, planned, wrong-resource, and
  catalogue-active but kernel-unimplemented actions fail closed.
- Ruff, stale Workstream wording, stale authorization documentation, changed
  Markdown links, and diff integrity passed.
- No workflow, dependency, package, test skip, coverage exclusion, or threshold
  changed. GitHub Backend remains authoritative for the repository-wide 78
  percent floor.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Decision invariants, actor lookup reuse, and request-scoped ownership are maintainable. |
| qa/test | PASS | none | Genuine API, denial, lifecycle, race, and negative behavior is covered without weakened tests. |
| security/auth | PASS AFTER FIXES | none | Unimplemented active actions deny and denial restaging is exact-service/exact-decision bound. |
| product/ops | PASS | none | Only actor self-read/self-update activate; suspended read remains available while update denies. |
| architecture | PASS AFTER FIXES | none | Feature code receives only the two-argument `require` interface; grants and project context remain deferred. |
| ci integrity | PASS | none | CI, dependencies, thresholds, skips, and exclusions are unchanged. |
| docs | PASS | none | Specification, operations, lifecycle, and OpenAPI action declarations match runtime behavior. |
| reuse/dedup | PASS AFTER FIXES | none | Canonical actor link/profile lookup is single-sourced. |
| test delta | PASS | none | Added tests prove fail-closed behavior and immutable decision contracts. |

## Findings Resolved

The first implementation review found that a future active action could inherit
the actor-self allow path, denial restaging was publicly callable with a
caller-created decision, allowed decisions could omit action/permission IDs,
and canonical actor lookup was duplicated. Repair `aabc0f4` closes all four:
the kernel explicitly recognizes only its two implemented actions, the
composition-root-only restage hook accepts only the exact pending decision from
the same service, allowed decisions require both identifiers, and verified
actor lookup delegates to the authorization lookup before lifecycle validation.

GitHub Backend run `29439489529` then exposed one stale historical audit test
that still assumed every catalogue action was planned. Repair `da0230c` keeps
the matrix exhaustive: the exact two active actor-self actions accept allowed
evidence, while every remaining planned action rejects it. The repair changes
no production behavior, workflow, threshold, skip, exclusion, or dependency.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining Gate

Ready PR publication, GitHub Backend, Agent Gates, CodeRabbit, and explicit
human merge approval remain pending. Do not start `WS-AUTH-001-08`
automatically.
