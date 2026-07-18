# WS-AUTH-001-06 PR Trust Bundle

## Chunk

`WS-AUTH-001-06` - Canonical Actor Profile And Identity Resolution

## Goal

Replace the legacy human registry as an authorization authority with one
canonical actor profile and issuer-subject identity link, while preserving a
strictly bounded compatibility bridge for existing submitter workflows.

## Human-Approved Intent

Every verified human receives one canonical profile. Authorization is based on
explicit authority and project grants, not a default contributor role. Human
product language uses contributor, submitter, and reviewer; worker remains only
for internal service execution or explicitly inventoried legacy identifiers.

## What Changed

- Migration `0020` classifies legacy identities, creates canonical actor
  profiles and identity links, enforces identity and lifecycle invariants, and
  provides guarded downgrade custody.
- Exact issuer-subject resolution serializes first access, atomically creates
  one profile/link plus authority evidence, and updates verification timestamps
  using database time.
- `GET/PATCH /api/v1/actors/me` exposes the canonical self-service contract;
  `/api/v1/auth/me` remains a compatibility view.
- Verified agent, service, and Space identities fail closed without actor state.
- First-access rate control now uses a shared dependency and maps unavailable
  infrastructure to a retryable, zero-write response.
- Legacy submitter compatibility is restricted to the existing profile,
  claim, start, and submission boundary and cannot become authorization truth.

## Why It Changed

Later grant and permission chunks require a stable actor reference that is not
coupled to email, mutable token display claims, or a legacy submitter record.
This chunk establishes that identity boundary before authorization policy is
activated.

## Design Chosen

External identity is keyed only by exact, bounded issuer and subject. Human profile
state is separate from identity links and defaults to active without assigning
a role. First creation is serialized with a PostgreSQL advisory transaction
lock. Runtime repositories do not own commits or sessions, and authority events
are written in the same transaction as actor state.

## Alternatives Rejected

- Email identity and Workstream-owned login were rejected because the external
  identity issuer owns authentication.
- A default contributor role was rejected because capabilities must come from
  explicit admin and project grants.
- Keeping the legacy registry authoritative was rejected because contributor,
  reviewer, and manager access must resolve through one canonical actor.
- Provisioning non-human principals through this route was rejected; later
  service-principal custody must be explicit.

## Scope Control

This chunk does not implement admin-role grants, project-role grants, the
permission evaluator, artifact-storage authorization, cache consumers, frontend
identity flows, or service-principal provisioning. Those remain in later AUTH
chunks.

## Product Behavior

A verified human is provisioned on first access and receives a stable actor ID.
They can read and update bounded display fields. Suspended identities remain
readable but cannot mutate; deactivated identities fail closed. Existing task
submitter flows continue through a compatibility projection while current
authorization remains unchanged until the grant and evaluator cutovers.

## Acceptance Criteria Proof

- Concurrent and repeated access produce one actor profile and one identity
  link with advancing verification timestamps and no duplicate authority rows.
- Unknown services and non-human identities are denied before persistence.
- Issuer and subject claims are consistently bounded at 200 characters across
  token parsing, verifier adapters, actor persistence, migration, and audit
  provenance.
- Migration upgrade, classification, constraints, indexes, privacy, guarded
  downgrade, re-upgrade, and terminal deactivation behavior have direct tests.
- Downgrade copies current canonical display fields, including a cleared email,
  so pre-AUTH-06 code cannot resurrect stale private data.
- Rate-control and audit failures roll back actor state and evidence together.
- Legacy activation is serialized and idempotent and audits only actual changes.
- Work-context claim, start, and submit affordances require the same current
  compatibility role and active eligibility as their mutation gates.

## Tests And Checks Run

- Actor subsystem branch coverage: 90.1031 percent across 804 statements and
  166 branches; 83 actor/classification behavior tests passed in 706.29 seconds.
- External-review migration, concurrency, lifecycle, exact-anchor, privacy, and
  zero-side-effect scenarios passed on the integrated branch.
- Real Postgres API contract: passed end to end through migration `0020`.
- Focused actor/auth/task/project/checker/rate-control behavior and migration
  suites passed; final coverage data includes the repaired static inventory and
  added repeated-access, unavailable-control, and compatibility assertions.
- GitHub Backend reached 983 passed tests and 83.11 percent repository coverage.
  Its only failure was the OpenAPI inventory still expecting the pre-AUTH-06
  route set; all 27 API-control tests pass with the two protected actor routes
  represented in the strict counts and hashes.
- Ruff, stale wording, stale authorization docs, changed Markdown links, diff
  integrity, all 71 engineering-loop agent-gate tests, loop-memory state, and
  the schema-v2 AUTH-06 merge-intent validator passed.
- The multi-hour repository suite was not repeated locally. GitHub Backend owns
  the authoritative full-suite result and repository-wide 78 percent floor.

## Test Delta

Tests replace obsolete registry-authority assumptions with canonical actor
behavior and add concurrency, rollback, privacy, lifecycle, migration, and
compatibility proof. No skip, xfail, coverage threshold, or meaningful
assertion was removed or weakened.

## CI Integrity

No workflow, dependency, package script, coverage exclusion, or threshold
changed. The actor subsystem meets its 90 percent branch gate, and GitHub must
still enforce the repository-wide 78 percent baseline.

## Reviewer Results

Exact reviewed code SHA `25d9455f6dca41b207a0ba3aaba8de9cc2683a17`
passed senior
engineering, QA/test, security/auth, product/ops, architecture, CI integrity,
docs, reuse/dedup, and test-delta review with no blocking findings.

## External Review

CodeRabbit's seven inline findings and three nitpicks were triaged. All valid
runtime, migration, lifecycle, privacy, test-harness, and test-contract findings
were repaired. Its generic diff-local docstring percentage is not the
repository's configured gate and required no narration-only churn. GitHub checks,
the next CodeRabbit head, the Backend rerun, and human review remain pending.

## Remaining Risks

- Database-owner or DDL credentials can bypass normal-DML guards; production
  must use the documented non-owner runtime role.
- Migration `0020` requires a quiesced deployment because it classifies and
  swaps legacy identity storage.
- Deactivation is terminal for downgrade purposes and requires forward recovery.
- The compatibility projection remains until its owning cutover chunk removes
  the legacy route and storage.

## Follow-Up Work

After merge, automated post-merge memory, stop, and a separate human start,
AUTH-07 may implement the next approved authority boundary. Later chunks own
admin grants, project grants, the evaluator, API cutovers, artifact-storage
authorization, and invalidation consumers.

## Human Review Focus

Review migration classification and downgrade custody, first-access transaction
and rate-control behavior, issuer-subject bounds, non-human zero-write denial,
and the exact limits of the legacy compatibility bridge.

## Human Merge Ownership

Only the human may approve and merge this PR. Internal or external checks do
not authorize merge.
