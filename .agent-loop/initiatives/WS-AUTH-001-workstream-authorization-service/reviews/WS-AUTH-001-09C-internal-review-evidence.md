# WS-AUTH-001-09C Internal Review Evidence

Reviewed code SHA: `2f4711fd55462898c32f82489a149ae53d6af192`

Reviewed implementation SHA: `4331a6aec2f70d2efb001cb1d61bf1541bea36b9`

Reviewed against trusted main:
`a10d9018007d2e847b4870e9b26cbd24e24c7bb4`

Reviewed at: `2026-07-18T05:11:01Z`

Reviewer run IDs: `auth_xint_roles`, `auth_xint_art_service`,
`auth_xint_rev_con`

Reviewer tracks: senior engineering, QA/test, security/auth, product/ops,
architecture, CI integrity, docs, reuse/dedup, and test delta

## External Repair Exact-Head Addendum

- PR #146's original Backend, Agent Gates, and CodeRabbit checks passed.
  CodeRabbit run `313d93f6-0386-4cce-97a6-d9442bdeebb3` produced five valid
  proof findings against published head `f08f443`.
- Test-only repair `c64bcc7` correlates the exact transition PostgreSQL backend,
  asserts exact self-target timestamp updates and authorization-kernel facts,
  and covers both routes for missing-resource rollback and project-scoped Audit
  Authority denial.
- Trusted main through PR #141 at `a10d901` is integrated. The fresh isolated
  database upgraded through migration `0025_artifact_store_v2`; 2 real
  PostgreSQL lifecycle/race tests passed in 241.10 seconds. Ten focused route
  and kernel unit tests, Ruff, and all 80 Agent Gates passed.
- Internal review found and repaired two additional lifecycle-gate defects: stale
  AUTH-09C/ART-02A3 queue prose and an initially overbroad negative phrase
  assertion. The final gate rejects only the exact obsolete normalized
  sentences and preserves both pre-merge ART branches.
- Senior engineering, QA/test, security/auth, product/ops, architecture, CI
  integrity, docs, reuse/dedup, and test-delta tracks all pass exact reviewed
  lifecycle head `2f4711fd55462898c32f82489a149ae53d6af192` with no open
  findings. No AUTH or ART production behavior, workflow, dependency, threshold,
  skip, or exclusion changed.

## Original Implementation Deterministic Evidence

- The original implementation review used `e118e33` as its merge base. PR
  #144's WS-CON specification, ADR, review evidence, inventory, and merge intent
  were preserved unchanged.
- The catalogue remains 74 PermissionIds and 65 ActionIds: exactly 12 active and
  53 planned. This chunk activates only `actor.profile.read` and
  `actor.identity_link.read`.
- Only an effective system-scoped Access Administrator or Audit Authority grant
  authorizes either exact target. Project-scoped Audit Authority is denied before
  target lookup.
- Separate frozen resource contexts enforce exact action/read-kind pairing. The
  caller profile, exact link, and matched grant are locked through disclosure and
  commit without `AuthorityControl` or target-row locking.
- Authorized reads expose strict bounded profile/link schemas. Tests exclude
  issuer, subject, contact, lifecycle reasons and actors, tokens, grants,
  assignments, and static service-action membership from responses and logs.
- Human targets return null `service_identity`; service targets return only the
  exact closed local identity. Unverified service timestamps remain null.
- Self-target profile and link reads return database-refreshed caller timestamps,
  stage one caller touch, and persist exactly one allow decision per request.
- Persisted allow evidence binds the exact action, permission, target UUID,
  matched system grant, request ID, correlation ID, caller, and allowed fact.
- Missing actor and link targets share one 404 envelope and roll back the staged
  allow decision and caller timestamps.
- Injected authorization-evidence, target-lookup, caller-touch, and commit
  failures on both routes return the retryable 503 envelope with no partial
  evidence or timestamp advancement.
- Two-session lifecycle, link, and matched-grant races observe a real PostgreSQL
  lock wait before releasing the read. The read linearizes before the disabling
  change, and the next request is denied without advancing timestamps.
- The real signed-token lifecycle and race selection passed 2 tests in 165.38
  seconds. The final privacy/evidence repair test passed in 60.67 seconds.
- The live HTTP API contract drill passed and exercised both routes for human and
  fixed-service targets without external identity disclosure.
- Actor branch coverage passed 145 tests at 91.06 percent. Authorization branch
  coverage passed 136 tests at 92.04 percent. GitHub Backend remains responsible
  for the repository-wide 78 percent floor.
- Ruff, exact route/kernel/OpenAPI/audit tests, merge-intent validation, stale
  Workstream/authorization/artifact scans, Markdown links, diff integrity, and
  all 80 Agent Gates tests pass. No threshold, skip, exclusion, workflow, or
  dependency was weakened.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Current main is integrated; the bounded routes, response freshness, and transaction ownership are coherent. |
| QA/test | PASS AFTER FIXES | none | Behavior tests prove exact evidence, privacy, rollback, self-target semantics, and deterministic lock races. |
| security/auth | PASS AFTER FIXES | none | Authority is system-only, target lookup follows authorization, and private identity/provenance data remains concealed. |
| product/ops | PASS | none | Authorized operators can inspect exact lifecycle targets without list/search or mutation behavior. |
| architecture | PASS AFTER FIXES | none | Action-specific contexts and central AUTH ownership remain intact without target locks or compatibility paths. |
| CI integrity | PASS AFTER FIXES | none | The lifecycle-only Agent Gates update preserves all 80 tests and all coverage floors. |
| docs | PASS AFTER FIXES | none | Specification, operations, chunk, counts, and authored state match the reviewed runtime. |
| reuse/dedup | PASS | none | ActorService and existing ActorRepository exact lookup methods are reused without duplicate SQL. |
| test delta | PASS AFTER FIXES | none | Tests add assertions and failure/race proof; none are skipped, weakened, or rewritten to hide behavior. |

## Findings Resolved

Valid findings addressed: yes

Open sub-agent sessions: none

The original exact-head review rejected a stale-main candidate and identified
incomplete SQL-stage, self-target, deterministic-race, persisted-evidence, and
log-privacy proof. Current main was integrated without discarding WS-CON. The
repair refreshes self-target response timestamps after the one caller touch,
observes PostgreSQL lock waiting instead of sleeping, covers every failure stage
on both routes, binds audit IDs to response headers, and scans actual token,
grant, identity, contact, reason, and provenance canaries. A final lifecycle-only
Agent Gates assertion was aligned from `In progress` to `In review`; all 80
tests pass.

## Remaining Risk And Gate

These APIs intentionally expose exact lifecycle timestamps and the closed local
service identity to system authorities. They do not expose external identity,
grant contents, list/search, mutation, or service admission. Replacement GitHub
Backend, Agent Gates, CodeRabbit, and explicit human merge approval remain
external gates. AUTH-09D must not start automatically.
