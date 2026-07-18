# WS-AUTH-001-07A Internal Review Evidence

Reviewed code SHA: `6f1b7ce5171d763cff2b5d6393784f80d4248187`
Reviewed runtime SHA: `3365e67e7b44195069a5c7645fdee0af1d4e0180`
Reviewed at: `2026-07-15T12:51:26Z`
Reviewer run IDs: `auth06_final_ci`, `auth06_final_docs`,
`auth06_final_test_delta`

## Deterministic Evidence

- The focused authorization and audit suite passed all 37 collected behavior
  tests against isolated PostgreSQL migration head `0021_auth_action_evidence`.
- Branch-aware subsystem coverage is 95 percent for authorization and 93
  percent for audit, above the required 90 percent threshold for materially
  changed backend subsystems.
- The exact catalogue/startup matrix covers the independent 49 historical and
  25 new PermissionId sets, exact 50-action mapping, missing,
  duplicate, extra, and hostile typed rows, immutability, and planned-action
  non-executability.
- The complete isolated Alembic suite passed 16 tests in 503.16 seconds at
  runtime SHA `3365e67`. It proves upgrade/downgrade/re-upgrade, historical-row
  preservation, exact restored permission behavior, all forward-evidence
  refusal paths, and the concurrent insert lock.
- Direct SQL accepts all 50 exact action/permission pairs as denied evidence,
  rejects all 50 wrong registered-permission pairs, and rejects all 25 new
  permissions without a mapped action.
- Amendment proof confirms typed validation rejects allowed evidence for all 50
  planned actions while PostgreSQL accepts all 50 exact allowed pairs as
  availability-neutral storage. The targeted isolated migration test passed in
  43.53 seconds at runtime SHA `3365e67`.
- Ruff, stale Workstream wording, stale authorization documentation, changed
  Markdown links, loop-memory state, and diff integrity passed.
- No workflow, dependency, test skip, coverage exclusion, package script, or
  threshold changed. GitHub Backend remains authoritative for the repository-
  wide 78 percent floor.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Closed catalogue, migration custody, and bounded test helpers are maintainable. |
| qa/test | PASS AFTER FIXES | none | Exact typed and SQL matrices, historical preservation, rollback paths, and concurrency are covered. |
| security/auth | PASS AFTER FIXES | none | No action is active; unknown or mismatched identifiers and unsafe rollback fail closed. |
| product/ops | PASS | none | No contributor, reviewer, project, artifact, or workflow capability is activated. |
| architecture | PASS | none | AUTH-07A remains a dependency-free catalogue and audit boundary; kernel and resource composition remain deferred. |
| ci integrity | PASS | none | CI, thresholds, dependencies, exclusions, and skips are unchanged. |
| docs | PASS | none | Contract, specification, operations, lifecycle, and rollback language match runtime behavior. |
| reuse/dedup | PASS | none | Audit validation consumes the single catalogue instead of retaining a second permission registry. |
| test delta | PASS AFTER FIXES | none | Assertions independently prove exact sets and exhaustive negative behavior without weakening prior tests. |

## Findings Resolved

Review repair added downgrade custody for new permissions stored in target and
invalidation permission-registry references. It also replaced count-only proof
with independent exact permission sets, made SQL negative coverage exhaustive,
completed startup failure cases, and proved a populated `0020` row survives
upgrade and clean downgrade with null action evidence.

The final exact-head review confirmed that `478a819..f35f71b` contains only six
lifecycle/merge-intent files, records the evidence accurately, and keeps
`WS-AUTH-001-07B` inactive until merge, signed memory, and explicit human start.

External repair review at `6287f57` confirmed CodeRabbit's proposed denial-only
SQL constraint would contradict the approved availability-neutral migration
contract. The review/revision amendment at `3365e67` adds one permission and 20
planned action dependencies without runtime authority. Exact-head repair
`160af8a` removes duplicate session authority: the request-scoped service binds
the caller-owned session once and exposes only
`require(action_id, typed_resource_context)`. Evidence-only head `f5af798` then
passed exact lifecycle, docs, and test-evidence review. Latest-main merge and
checkpoint repair head `6f1b7ce` then passed merge-integrity, architecture, QA,
CI, lifecycle, and docs confirmation without AUTH runtime changes.

Valid findings addressed: yes

Open sub-agent sessions: none

## Remaining Gate

PR #126, GitHub Backend, Agent Gates, CodeRabbit, and explicit human merge
approval remain pending. Do not start `WS-AUTH-001-07B` automatically.
