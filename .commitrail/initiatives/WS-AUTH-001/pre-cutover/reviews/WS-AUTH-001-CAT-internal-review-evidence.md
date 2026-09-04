# Internal Review Evidence: WS-AUTH-001-CAT

## Chunk

`WS-AUTH-001-CAT` - Action And Resource Catalogue Reconciliation

Primary affected implementation owner: `WS-AUTH-001-07`; later surface owners
are `WS-AUTH-001-08` through `WS-AUTH-001-16` as recorded in the chunk map.

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: `fdd1f3db353993bf489fda45b4c7c3ae8eef858c`

Reviewed at: 2026-07-14T15:16:43Z

Reviewer run IDs: senior-engineering-architecture-docs=WS-AUTH-001-CAT-EXT-ENG-20260714;
qa-test=WS-AUTH-001-CAT-EXT-QA-20260714;
security-auth-privacy-product-ops=WS-AUTH-001-CAT-EXT-SEC-20260714

## Scope

Docs/specification-only reconciliation of the proposed action/resource catalogue
against merged Workstream models, routes, audit constraints, domain ownership,
and the approved AUTH chunk sequence. No runtime, migration, CI, dependency, or
test file changed.

## Initial review disposition

The proposed root document failed review and was removed. It incorrectly claimed
normative precedence, used `/v1`, replaced adopted permission identifiers,
invented artifact/review/compensation resources, conflicted with the merged audit
registry, and required all loaders before their domains exist.

Validated design material was retained only after repair:

- exact `ActionId` declarations map to approved `PermissionId` values;
- multiple actions may use one retained broad permission with distinct targets;
- feature-owned services compose closed typed resource contexts;
- creates authorize against an existing parent or `system` target;
- planned action metadata is non-executable and domain-neutral;
- every route-owning chunk proves its manifest delta and 90 percent AUTH coverage;
- AUTH-16 aggregates, rather than first discovers, surface coverage;
- fixed service principals and pre-count filtering remain mandatory; and
- action identity is carried in decisions, bounded telemetry, and audit evidence.

## Findings repaired

1. Distinguished 52 approved permission identifiers from AUTH-05A's current
   49-identifier typed/PostgreSQL audit base. AUTH-13/14 own additive parity for
   the three already-approved recovery identifiers before activation.
2. Separated exact `ActionId` from `PermissionId`, allowing precise targets and
   guards without an unapproved permission rename.
3. Limited planned metadata to stable action/permission IDs, owner, and
   availability; foreign-domain resource facts remain with their specifications.
4. Added per-chunk manifest-delta proof and 90 percent authorization-subsystem
   coverage requirements from AUTH-07 through AUTH-16.
5. Required closed typed resource variants, exact concealment precedence, and an
   explicit mutation/revocation linearization contract.
6. Added `ActionId` to decision/evidence requirements under AUTH-07 migration
   `0021`, including historical compatibility and exact typed/SQL registry proof.
7. Reconciled migration custody: `0018` AUTH-05A, `0019` AUTH-05B, then
   `0020` through `0026` for AUTH-06/07/08/10/12/13/14.
8. Removed the rejected untracked root proposal to prevent accidental staging or
   discovery as a second authority.
9. Exact-SHA security review found a low-risk stale AUTH-05B start gate in the
   durable state files. They now record the received signal and exact remaining
   CAT merge/post-merge-memory prerequisites consistently.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Dalton confirmed ActionId evidence and migration custody. |
| qa/test | PASS | None | Locke confirmed manifest, coverage, audit parity, and migration proof allocation. |
| security/auth | PASS after fixes | None | Sagan confirmed source removal, privacy, planned/active boundaries, and reconciled the AUTH-05B gate. |
| product/ops | PASS | None | Sagan confirmed human/service and domain-lifecycle ownership. |
| architecture | PASS | None | Dalton confirmed staged ownership and collision-free migrations. |
| docs | PASS | None | Dalton confirmed canonical precedence and domain boundaries. |

All reviewer sessions completed. No unresolved findings remain.

## External repair confirmation

The three required internal reviewer groups re-reviewed exact repair SHA
`fdd1f3db353993bf489fda45b4c7c3ae8eef858c` and passed. External findings and
their dispositions remain separately recorded in
`WS-AUTH-001-CAT-external-review-response.md`.

## Deterministic evidence

Passed:

```text
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
git diff --check
```

No backend test suite was run because the patch contains only Markdown planning
and specification changes. It adds future test/coverage requirements and does
not modify tests, CI, dependencies, thresholds, skips, or exclusions.
