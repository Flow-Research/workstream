# WS-AUTH-001-07 Preimplementation Plan Review

## Initial verdict

`FAIL` before runtime implementation.

## Review tracks

| Track | Result | Blocking findings |
|---|---|---|
| senior engineering / architecture / reuse | FAIL | Combined catalogue, migration, kernel, APIs, manifest, and transaction proof were not one bounded L1 change; required ORM and route files were omitted. |
| security/auth / product/ops / docs | FAIL | Grant-backed and project-scoped APIs preceded authority sources; active actions, denial precedence, transaction ownership, response privacy, and planned artifact boundaries were incomplete. |
| QA/test / CI integrity | PASS WITH CONDITIONS | Missing allowed tests, exact action tables, migration versioning, synchronized race proof, isolated-test runner contract, and changed-subsystem 90 percent coverage. |

No application, migration, dependency, workflow, or test code was changed before
these verdicts.

## Valid repair

- Split parent AUTH-07 into AUTH-07A and AUTH-07B.
- AUTH-07A owns exactly 73 PermissionIds, 30 four-field planned ActionIds, and
  migration `0021` action-aware audit parity. No action is executable.
- AUTH-07B owns the minimal deny-by-default kernel and activates exactly
  `actor.profile.read_self` and `actor.profile.update_self` on the existing
  `/api/v1/actors/me` routes.
- Permission/admin-role definition APIs move to AUTH-08.
- Project-scoped authorization context moves to AUTH-10.
- Feature loaders, grant matrices, concealment, and revoke races remain with
  their owning cutovers.
- Verification uses `WORKSTREAM_TEST_ADMIN_DATABASE_URL`, the isolated-test runner,
  branch coverage at or above 90 percent for materially changed subsystems, and
  the unchanged repository-wide 78 percent CI floor.

## Second repaired review

Exact-SHA senior engineering, architecture/reuse, QA/test, and CI-integrity
review passed `b1b47b0`. Security/auth, product/ops, and docs review found one
remaining audit-integrity blocker before runtime implementation:

- the contract admitted registered actions and permissions independently rather
  than enforcing the exact action-to-permission mapping;
- a newly admitted permission could be stored without an action, so the guarded
  downgrade predicate was incomplete; and
- planned actions were not explicitly barred from allowed-decision evidence.

The next candidate closes those findings in both typed and PostgreSQL
acceptance criteria, requires denial-only evidence for planned actions, and
checks both action and post-`0018` permission evidence under the exclusive
downgrade lock. No runtime code was written.

## Third repaired review

Exact-SHA architecture/reuse and CI review of `8690ef5` confirmed the mapping
and downgrade repair but rejected one temporal-schema ambiguity. The contract
could be read as freezing planned actions to denied events in PostgreSQL, which
would prevent AUTH-07B from activating its two self actions without another
migration. The repair makes availability a typed catalogue invariant only.
PostgreSQL remains stable across activation and enforces registration,
decision-event-only use, and exact action-to-permission mapping. Direct-SQL
planned-action fixtures use denied evidence without asserting a database-level
availability rule. No runtime code was written.

## Re-review gate

`PASS` at exact planning SHA `beb85ac9d7d6ad0f7f12630cf3e8fdc4df8ac3f7`.

Senior engineering, architecture/reuse, security/auth, product/ops, docs,
QA/test, test-delta, and CI-integrity review found no remaining blockers. The
reviewed contract keeps availability in typed validation, keeps PostgreSQL
availability-neutral, closes exact action-to-permission mapping and downgrade
custody, and preserves the 07A/07B/08/10 ownership boundaries.

Deterministic planning evidence at the reviewed SHA:

- 71 agent-gate tests passed with third-party pytest plugin autoload disabled;
- Markdown links passed;
- stale Workstream wording passed;
- stale authorization documentation passed; and
- `git diff --check` passed.

Bounded AUTH-07A runtime implementation may begin. Prior failed results remain
historical evidence and do not approve code outside this contract.
