# WS-AUTH-001-12 PR Trust Bundle

## Chunk

`WS-AUTH-001-12` - Project Mutation Authorization Cutover Planning

## Goal and human-approved intent

Repair the rejected combined AUTH-12 contract before runtime work, preserve the
critical authorization boundary, and make every implementation unit explicit,
bounded, independently reviewable, and fail closed. The user explicitly
started AUTH-12 after AUTH-11C2 merged.

## What changed and why

- Inventories eighteen exact mutation actions, permissions, principals, and
  activation owners.
- Splits the work into ten ordered children: catalogue/PREP foundation, fixed
  setup-service identity, project creation, guide metadata, review/revision
  policy, sufficiency, submission artifact policy, post-submit policy, setup
  runtime cutover, and guide activation.
- Separates zero-activation service provisioning (12B) from the final Celery
  call-graph cutover (12B2).
- Requires opaque transaction-bound PREP consumption, canonical lineage,
  single-use/idempotency bindings, atomic evidence, and fail-closed denial.
- Requires setup-service actions to bind the exact active run, step,
  task/correlation, project lineage, generation, stale-output digest, and
  service matrix provenance. Public routes do not accept service identity.
- Keeps active ART guide ingestion outside AUTH-12 and keeps retired economic
  policy under CON ownership.
- Adds one exact scanner exemption solely to name the real 12B2 Celery module
  path in its contract.

The inherited combined implementation was rejected because it mixed catalogue,
service identity, human routes, agent boundaries, provenance migrations, and
terminal activation in one unreviewable change. Compatibility and generic
authorization alternatives are explicitly rejected.

## Scope control and product behavior

This PR changes planning, durable initiative memory, child contracts, review
evidence, and one narrow documentation scanner exemption. It changes no
application behavior, migration, action availability, route, database state,
test, or CI workflow.

## Acceptance proof and test delta

- All eighteen current mutation/setup actions appear exactly once.
- All ten child contracts state prerequisites, file custody, exclusions,
  acceptance criteria, risk, reviewers, human focus, and stop conditions.
- All nine required internal reviewer tracks pass after valid findings were
  repaired.
- Diff integrity, Markdown links, stale authorization wording, and stale
  Workstream wording passed on the repaired tree.
- No tests changed. Each runtime child must replace verification placeholders
  with exact commands before implementation and must preserve 90 percent
  changed-module and repository-wide 78 percent coverage obligations.

## CI integrity and external review

No workflow, test selection, package script, coverage floor, lint/typecheck
rule, or dependency changed. The scanner exemption uses full-line matching for
one path in one planning file. GitHub full checks and CodeRabbit remain pending
until the branch is pushed.

## Remaining risks and follow-up

Implementation correctness remains intentionally deferred to the children.
12A cannot allocate a migration until ART-owned migration `0040` merges. 12H
also waits for the CON-owned removal of the retired guide-bound economic-policy
dependency. Planning artifacts do not activate or lock either dependency.

After this planning PR merges, a child requires a separate user start. The
immediate candidate is 12A only when its migration prerequisite is present on
trusted main.

## Human review focus

Review the eighteen-action inventory, ten-child dependency order, distinction
between human HTTP and fixed-service authority, exact setup-run custody,
ART/CON ownership boundaries, and the absence of runtime activation.

## Human merge ownership

The agent may publish and repair this branch but may not merge it. Only the user
may approve this specific PR for merge.
