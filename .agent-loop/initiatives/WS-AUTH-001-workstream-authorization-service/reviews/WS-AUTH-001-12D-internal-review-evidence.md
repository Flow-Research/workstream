# WS-AUTH-001-12D Internal Review Evidence

## Scope reviewed

Draft guide create/update and guide-source snapshot metadata creation through
the existing PREP protocol, migration 0045 custody, clean-cut activation-route
removal, and temporary isolated-test downstream activation seeding.

## Deterministic evidence

- Ruff and `git diff --check`: pass.
- Markdown links, stale Workstream wording, and stale authorization docs: pass.
- Focused PostgreSQL AUTH-12D lane: 20 passed.
- Exact key-before-provisioning and project-scope regression: 2 passed.
- Snapshot header/item and lineage custody regression: covered in the focused lane.
- Real API contract E2E: pass, including public activation-route 404.
- Hosted full-suite and per-file 90 percent coverage gates: pending pushed SHA.

## Reviewer results

| Track | Result | Material resolution |
| --- | --- | --- |
| Architecture | PASS | Synced current main, preserved ART gates, bounded temporary test seed, and made guide lineage immutable. |
| Security | PASS | Key-gated actor/PREP chain; exact binding; immediate lifecycle guard; full snapshot-item custody. |
| QA | PASS | Reset guards, append/update/delete/truncate proof, activation cutover, and E2E expectations reconciled. |
| Product/ops | PASS | Activation is explicitly deferred to AUTH-12H; only three 12D actions are exposed. |
| Senior engineering | PASS with low risk | Shared actor/PREP helpers preserve structured denial handling; isolated seed restores both triggers. |
| CI integrity | PASS with low risk | Existing floors remain; three new modules receive hosted per-file 90 percent gates. |
| Docs | PASS | Link and stale-wording gates pass; guide/setup wording matches the cutover. |
| Reuse/dedup | PASS with low risk | Manifest, item construction, and validation use shared implementations. |
| Test delta | PASS with low risk | No skips or weakened assertions; missing/malformed key and migration round-trip proof restored. |

All reviewer sessions completed. No Critical, High, or Medium finding remains open.

## Corrective-delta re-review

After the first hosted run and CodeRabbit review, architecture, security, QA,
product/ops, senior engineering, and CI integrity re-reviewed the corrective
delta. All six tracks passed with no blocking finding. They confirmed:

- explicit null and omitted guide-update fields have distinct replay digests;
- trigger restoration rolls back first and remains isolated-test-only;
- downstream policy prerequisites are independent from the clean-cut guide API;
- system and exact-project Project Manager grant paths are both covered;
- removing the dead `ProjectService` snapshot/setup helper chain leaves setup
  dispatch in its intended mutation-router boundary; and
- no CI or coverage gate was weakened.

All corrective re-review sessions completed.

After the second hosted failure, architecture passed the final delta. Security
and QA each found and then verified closure of one blocking E2E edge case:
suffixed package credential refs now fail closed, and activation seeds resolve
the exact run-specific Flow subject plus issuer to its canonical actor profile.
Both final tracks passed, and all sessions completed.

After the third hosted run exposed ART guide-binding fixtures that constructed
pre-0045 lineage against the current custody schema, architecture, security,
and QA reviewed the bounded corrective delta. The chunk contract now explicitly
includes `backend/tests/test_guide_bindings.py` for that downstream regression
repair. Focused isolated-database proof covers both historical lineage setup and
the migration downgrade/current-model boundary; production custody triggers
remain unchanged.

Security's blocking review finding tightened the fixture from a database-name
prefix check to the runner-owned `workstream_test_<12 hex>` and matching
`workstream_role_<12 hex>` pair. QA's blocking finding identified three later
setup-generation inserts; all now use the same bounded fixture. Security passed
the correction, and the exact three QA regressions pass in an isolated database.

The fourth hosted run exposed the same historical-lineage assumption in shared
ART admission and recovery fixtures, plus one migration-0028 test that used the
current ORM while intentionally holding the old schema. Those fixtures now use
the strict runner-owned suspension; the migration test uses only columns that
exist at 0028. The newly active action set and guide-router dependency are also
represented in their static contract assertions. Four representative database
regressions and both static assertions pass. Architecture, security, and QA
re-reviewed the expanded correction and all passed with no open finding.

The fifth hosted run left one stale lock-only assertion: 1,862 shared-foundation
tests passed, while immutable guide/item mutations denied before the expected
lock timeout. The correction now accepts only the two safe outcomes appropriate
to each row (held lock or the named immutable/lifecycle guard) and uses the
strict isolated fixture for the final historical status transition. The exact
regression passes locally. Fresh CodeRabbit review also identified and prompted
closure of the remaining weak isolation check and over-broad secret-name prefix.

Product review then found the same prefix issue in the earlier durable-ref
scanner. Whole-token boundaries now apply there as well. The complete focused
source-ref proof passes: 46 unsafe credential/local refs deny and three benign
secretary/tokenizer/credentialing refs are accepted. Product re-review passed;
security and QA also passed the final CodeRabbit/hosted-CI correction with no
open finding.

The sixth hosted run completed every semantic lane except one migration replay
test. That test documented migration 0038 but upgraded to head before creating
0038-era rows, causing the intentionally strict 0045 guide mutation trigger to
deny the seed. Setup and replay verification now remain at revision 0038; the
production trigger is unchanged, and the exact migration regression passes.
Architecture and QA re-reviewed this final narrow delta and passed it with no
finding; all reviewer sessions completed.

The seventh hosted run passed every semantic lane and then found the shared
authorization dependency at 88.44 percent in the existing project-cutover
per-file gate. Direct regressions now cover authorization-evidence failure,
database failure, and cancellation across the PREP context manager, including
rollback and opaque-handle closure. The 90 percent gate remains unchanged.
QA passed the failure-semantics proof, and CI integrity passed with only the
expected low risk that the new exact head still requires hosted verification.
Both review sessions completed with no required fix.
