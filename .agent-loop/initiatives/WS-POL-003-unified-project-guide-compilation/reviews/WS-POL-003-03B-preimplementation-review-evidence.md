# WS-POL-003-03B Preimplementation Review Evidence

Date: 2026-08-21. Risk: L1. Runtime implementation: not started.

## Review target

- Authoritative base: `c716fa424c1a86bda9e0f85c77c307fa07172bca`.
- First contract head: `4a749b46aadb1207b367ebaf175b6945f3054cc8`.
- Remediated contract head: `f6d3fd265c08693d0a747df080f4240469ea9832`.
- Both reviewer groups ran `python3 scripts/review_target.py` at the start and
  end of each review. The recorded base/head/merge-base matched, and the
  worktree was clean.
- Reviewer receipts are read-only session evidence. This durable file records
  their findings, dispositions, commands, and verdicts without fabricating a
  self-referential Git receipt.

## Findings and resolution

| Finding | Severity | Resolution | Remediated result |
|---|---|---|---|
| PostgreSQL could not prove the request digest preimage from the original draft | High | The contract now requires two exact PROJECTS-owned SQL functions using built-in PostgreSQL SHA-256, byte-for-byte parity with the public Python helpers, null/non-null predecessor cases, and mutation of every bound input. The custody trigger compares both the facts and authority digests. | Closed |
| The obsolete POL-03A deny-only authorization seam could remain as a second adapter | Medium | The contract now requires deletion of the temporary seam and a syntax-aware test proving no production or test import remains. No alias or fallback is allowed. | Closed |
| The semantic-lane instruction lacked a runnable exact command | Medium | The command block now creates a task-local temporary directory and supplies the required metadata, summary, and `project_lifecycle` arguments. | Closed |
| Initiative decisions overstated provider recovery | Low | `DECISIONS.md` now records `provider_outcome_unresolved`, no redispatch, and a separate proof requirement before future same-key retrieval/reuse. | Closed |

## Final reviewer verdicts on the remediated contract

| Track | Verdict | Primary evidence focus |
|---|---|---|
| Architecture | PASS | Owner/consumer/public-port matrix, exact SQL digest custody, hidden composition, transaction and external-I/O boundaries |
| Reuse/dedup | PASS | Reuse of AUTH-12I and POL-03A, retired deny seam, no generic operation/provider/outbox framework |
| Security/authorization | PASS | Actor/action/resource/state substitutions, SQL/Python digest parity, audit/event rollback, replay, and data safety |
| QA | PASS | Atomic effects, real-PostgreSQL concurrency, crash/recovery, exact row counts, and forbidden-effect absence |
| Test delta | PASS | Per-field and seeded-defect probes, syntax-aware seam removal, one primary invariant, no mock-only lifecycle evidence |
| Senior engineering | PASS | Feasible PostgreSQL 16 design, failure taxonomy, short root transactions, conservative provider uncertainty, runnable commands |
| CI integrity | PASS | Exact project-lifecycle registration, seven-lane fan-in, 78/90 coverage floors, and no weakened gate |
| Product/operations | PASS | Operator-visible unresolved state and no false setup, approval, guide, review, or economic truth |
| Documentation | PASS | Current-main decisions, exact command truth, terminology, Markdown links, and deferred POL-04A ownership |

Each track supplied atomized requirement/owner/proof traceability, distinguished
executed from inspected evidence, replayed its prior findings, and stated a
residual escape hypothesis with a discriminating test-of-the-test probe. No
Critical, High, Medium, Low, or Informational finding remained after the
remediated review.

## Executed evidence

```text
python3 scripts/review_target.py --base c716fa424c1a86bda9e0f85c77c307fa07172bca --head <reviewed-head>
git diff --check c716fa424c1a86bda9e0f85c77c307fa07172bca..<reviewed-head>
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
```

Reviewers also executed bounded static probes for AUTH/POL ownership, current
deny-seam references, provider/worker/route reachability, the lane-runner CLI,
seven-lane inventory, and coverage gates. They inspected the merged AUTH public
facts/adapter, POL-03A repository/model/validator, audit schema, current
migration head, initiative state, and pinned PostgreSQL 16 runtime.

No application runtime, migration, test, CI workflow, dependency, worker,
provider, route, generated artifact, push, pull request, or merge was created
during this planning review.

## Repair 1: Alembic head-parity scope

The first Phase 3 drift check stopped cleanly before edits. The implementation
contract allocated migration 0008, while `backend/alembic/env.py` recognized
only 0007 and was absent from the allowed files. Leaving it unchanged would
make a later Alembic run reject a database already migrated to 0008.

The contract amendment permits only replacement of the existing
`_CURRENT_HEAD_REVISION` value from 0007 to the exact 0008 revision. It also
requires proof that baseline and exact current-head recognition still work, a
second 0008 run is a no-op, unsupported revisions retain the existing
recreation failure, and every other `env.py` line remains unchanged. Dynamic
head discovery and any migration-policy change remain prohibited.

Repair 1 exact-head reviewer verdicts:

| Track | Verdict | Repair-specific conclusion |
|---|---|---|
| Architecture | PASS | One existing static head constant remains the sole mechanism; no dynamic discovery or second head path |
| Reuse/dedup | PASS | Reuses the current Alembic preflight and existing migration test owner |
| Security/authorization | PASS | No AUTH, transaction, provider, route, worker, or product authority boundary changes |
| QA | PASS | Baseline, 0008 current head, second-run no-op, unsupported revision, and source-only-change proofs are discriminating |
| Test delta | PASS | Exact test scope adds no skip, weakening, mock-only proof, or lane-topology change |
| Senior engineering | PASS | One-line runtime parity change is implementable and preserves recreation policy |
| CI integrity | PASS | Existing Alembic/lane/coverage gates remain authoritative and unchanged |
| Product/operations | PASS | Planning-only repair creates no live, provider, approval, setup, or economic truth |
| Documentation | PASS | Status and evidence accurately describe the stopped attempt and bounded amendment |

Both reviewer groups ran the repository target-integrity command at start and
end against planning head `2937c566c711a9395f483fc8f70b2ce9bfb5da24`;
base/head/merge-base matched and the worktree remained clean. Each track
reported no findings and supplied a residual escape hypothesis with a
discriminating probe.

No runtime, migration, test, CI, dependency, or Alembic environment file was
changed by this planning repair.

## Repair 2: Complete hard-coded-head scan

Phase 3 Retry 1 stopped cleanly before edits when the two existing domain
migration-contract tests were found to assert 0007 as the current schema head
while remaining outside the allowed list. Repair 2 permits only replacement of
those two current-head expectations with exact 0008. It does not authorize test
refactoring, broader migration cleanup, or any other change in those files.

The complete tracked-repository scan used exact-literal and generic
head-variable searches across executable checks, fixtures, scripts, workflows,
and documentation. Every exact 0007 match is classified below.

| Classification | Exact surfaces | Disposition |
|---|---|---|
| Needs current-head parity update; already admitted | `backend/alembic/env.py`; `backend/tests/test_alembic.py` | Replace only the current-head value with exact 0008 and retain existing policy/topology behavior |
| Needs current-head parity update; admitted by Repair 2 | `backend/tests/projects/guide_compilation/test_migration_contract.py`; `backend/tests/authorization/guide_compilation/test_migration_contract.py` | Replace only each current-schema expected revision with exact 0008 |
| Intentionally historical migration identity | `backend/alembic/versions/0007_contribution_policy_publication_custody.py` | Keep the immutable revision identifier unchanged; migration 0008 points back to it |
| Intentionally historical planning and handoff record | `WS-ARCH-001-CP04B-con-policy-publication-behavior.md` (two matches); `WS-CON-001/AUTHORIZATION_HANDOFF.md` | Keep as the reviewed CP04B delivery record and pre-0008 handoff snapshot |
| Intentional POL-03B starting-point and repair history | This chunk contract (current starting head plus 0007-to-0008 bounds); this review evidence | Keep as provenance explaining the required transition |

Generic searches found no additional executable sole-head literal. The
isolated-test runner discovers the sole Alembic head from the migration graph;
coverage/evidence validators compare caller-supplied or runner-observed values;
workflow and script calls to `alembic upgrade head` follow the graph; and older
initiative documents name their then-current revisions as historical evidence.
None requires a parity edit. No additional production, test, fixture, script,
workflow, or documentation surface is admitted.

The amended proof now fails if any of these four current-head authorities
disagrees: `backend/alembic/env.py`, the sole Alembic graph asserted through
`backend/tests/test_alembic.py`, the PROJECTS migration contract, or the AUTH
migration contract. Exact-final-head reviewer verdicts are pending.

## Phase 3 gate

Phase 3 is authorized only if all exact-final-head reviewer receipts remain
PASS and the contract's base, prerequisites, sole migration head, frozen AUTH
Protocol, provider limitation, and allowed scope still match. Any drift invokes
the contract's stop-and-re-review rule.
