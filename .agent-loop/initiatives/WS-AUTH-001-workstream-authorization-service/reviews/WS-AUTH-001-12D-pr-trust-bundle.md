# WS-AUTH-001-12D PR Trust Bundle

## Intent

Activate exactly `project.guide.create`, `project.guide.update`, and
`project.guide_source_snapshot.create` for a system-scoped or exact-project
Project Manager. Keep ART byte operations, policy mutation, and guide activation
outside this chunk.

## Design and scope

- Dedicated guide mutation router, service, and repository use the existing
  opaque, transaction-bound PREP protocol.
- Required UUID idempotency is validated before actor first-access provisioning.
- Prepared requests and final decisions bind actor, identity link, exact grant,
  action, project, guide, target resource, operation, transaction, generation,
  and current source lineage.
- Migration 0045 records atomic replay/evidence/product custody and protects
  guide identity/lifecycle plus the complete snapshot manifest/item set.
- The legacy activation route is absent until AUTH-12H. Downstream tests seed
  historical active state only inside derived isolated databases.

## Proof

- Focused PostgreSQL lane: 20 passed.
- Key ordering and exact project scope: 2 passed.
- Real API contract E2E: passed.
- Hosted CI failure was traced to downstream task/checker fixtures retaining the
  retired guide request shape. The corrected isolated PostgreSQL regression lane
  passed 9 tests across downstream setup, replay, and grant-scope paths.
- A second hosted run exposed remaining stale tests plus a shared durable-ref
  validation regression. The repair restores secret-reference rejection, uses
  canonical actor IDs in isolated activation seeds, and proves immutable
  snapshots reject legacy rewrites. Its exact local selection completed 36 tests
  without a failure before local execution was stopped for machine cost.
- Ruff, diff check, Markdown links, and stale wording/docs: passed.
- The final schema-lane failure was an old migration-0038 replay test running
  against head; its setup and replay checks are now pinned to 0038, and the
  exact isolated regression passes without weakening 0045 custody.
- All semantic lanes then passed; explicit PREP failure-path regressions close
  the remaining shared-dependency per-file coverage gap without lowering its
  90 percent threshold.
- The following hosted run confirmed that file at 91.84 percent and exposed a
  one-statement kernel gap; guide PREP scope/grant/service denials now have
  direct regression proof while the kernel's 90 percent gate remains intact.
- The next hosted run passed those repaired gates and exposed the new replay
  repository's untested fail-closed branches; eight direct repository cases now
  cover classification and custody-loss behavior without changing production.
- Internal architecture, security, QA, product, senior, CI, docs, reuse, and
  test-delta tracks: passed; low risks are documented in the review evidence.
- GitHub full-suite, repository 78 percent, AUTH 90 percent, and new per-file
  90 percent gates remain required on the final pushed SHA.

## Remaining risk and human review focus

- Confirm only the three intended actions moved from planned to active.
- Inspect migration trigger ordering, snapshot-item append protection, and the
  shortened Alembic revision id documented beside the exact migration filename.
- Inspect the key-gated actor/PREP dependency graph and denial restaging.
- Confirm the temporary activation seed is test/E2E-only and isolated-database guarded.

## External review response

- CodeRabbit's explicit-null idempotency finding was fixed with
  `exclude_unset=True` and a replay-mismatch regression.
- Trigger restoration now rolls back first in both isolated activation helpers.
- System and exact-project Project Manager paths are both covered for all three
  actions.
- Dead legacy snapshot/setup helpers were removed; downstream fixtures use the
  clean-cut guide contract and seed independent lifecycle policy prerequisites.
- Suffixed package-credential refs are rejected, and both API E2E flows bind the
  isolated activation seed to the exact admitted Flow subject and issuer.
- The complete response is recorded in
  `WS-AUTH-001-12D-external-review-response.md`.

Chunk complete locally. Await corrected-head hosted CI, CodeRabbit, and human merge.
