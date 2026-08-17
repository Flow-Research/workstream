# WS-ARCH-001-CP04A Implementation Trust Bundle

## Chunk and goal

Implement the hidden CONTRIBUTIONS-owned read, create-draft, and complete
update-draft capability without exposing a route or activating any of the five
registered ContributionPolicy actions.

## Human-approved intent

ContributionPolicy is prepared before task readiness. This chunk establishes
only its safe hidden draft boundary; CP04B owns publication/retirement and CP05
later owns authorization activation. It does not start the full CON lifecycle.

## What changed and why

- Added immutable CONTRIBUTIONS public requests, results, views, and owner
  ports; no ORM, repository, or session escapes the API.
- Moved the closed compensation instrument enum to its canonical public home.
- Added COMPENSATION and PROJECTS transaction-held public owner lookups and
  composed them only at adapter roots.
- Added hidden read/create/update behavior with complete graph replacement,
  advisory operation fencing, opaque prepare/consume/close authorization,
  immutable replay results, and caller-owned transaction custody.
- Added migration `0006_contribution_policy_operations` with immutable event
  guards and exact actor/lineage attribution.
- Removed the touched CONTRIBUTIONS-to-private-COMPENSATION import debt.

The service was split from pure validation/digest helpers so neither production
nor test behavior containers approach the 500-line ceiling.

## Scope and product behavior

The behavior is route-unreachable and production deny-default. It creates or
updates only one project policy draft and its complete rule/definition graph.
It does not publish, retire, mutate guide/task/submission/review/contribution or
award state, perform fulfillment/delivery/callback work, or project reputation.

## Acceptance proof

- The counts below are historical evidence from the preceding reviewed head;
  the substantive CodeRabbit corrections require fresh exact-head replay.
- 89 focused behavior tests passed before final additions; the contract-listed
  isolated regression set passed 155/155.
- Real PostgreSQL create/update/read, concurrency, and immutable-event proof
  passed 10/10.
- Combined CP04A coverage collection passed 186/186.
- Exact changed-surface coverage: CONTRIBUTIONS API 97%, models 100%, schemas
  91%, repository 95%, service 92%, validation 92%; all changed owner and
  composition surfaces are 92-100%.
- Module boundary, test-structure, state projection, chunk-state, Markdown,
  stale-document, Ruff, action-unavailability, and diff checks pass.
- The behavior-ownership partition includes exactly the nine new CP04A
  executable targets; its trusted transition rejects any additional target,
  and all 106 focused ownership tests pass.
- The unchanged repository docstring gate reports 80.8 percent after adding
  meaningful docstrings only to CP04A's new callables; Ruff passes, and the
  production service and repository remain below 500 lines.
- Migration-0005 tests use isolated schema-contract custody, and CP04A's
  create, update, and recovery tests compare all immutable mutation-result
  fields with lifecycle-event truth. Duplicate update recovery additionally
  proves read reauthorization, digest mismatch denial, and no second mutation.
- Adversarial exact-head replay found and corrected integer-scale
  project-points validation, exact COMPENSATION owner-fact parity, malformed
  rule concealment, and a missing real-PostgreSQL late-rollback proof.
- Reuse replay then found a fork between schema and behavior quantity bounds.
  Both now consume one CONTRIBUTIONS-owned canonical validator, and regression
  tests prove overflow/over-scale values stop before authorization or mutation.
- CP04A's authorization claim is deliberately narrow: opaque port rejection
  creates no product effect and every prepared object is closed once. CP05/AUTH
  owns real handle session, transaction, copy, and replay semantics.
- Substantive CodeRabbit replay added NULL-safe event custody, composite event
  ownership, real cross-project repository concealment, import-aware boundary
  proof, required-selector validation, and exact owner-fact mismatch tests.

GitHub's hosted semantic lanes own the full suite and unchanged 78% global
coverage threshold. No workflow, test selection, skip policy, dependency, or
coverage threshold was weakened.

## Review and external evidence

Internal reviewer receipts are private exact-head session evidence. This file
does not preclaim their verdicts; the PR body must mirror all required reviewer
results with the exact reviewed head. CodeRabbit and hosted CI must likewise be
reported as fresh, stale, rate-limited, skipped, or unavailable rather than
being inferred from a green status.

## Remaining risks and follow-up

CP04B must reuse this operation/event foundation for publish and retire without
adding a second protocol. CP05 may activate only the behavior proven by CP04A
and CP04B. CP06-CP08 later validate and carry the published policy through guide
activation and task-attempt lineage.

## Human review focus and merge ownership

Review complete graph replacement, operation/PREP ordering, event attribution,
duplicate recovery, public-owner isolation, and continued route/action absence.
Only an authorized human may approve and merge the PR.
