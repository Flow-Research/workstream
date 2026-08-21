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

Repair 1 exact-head reviewer verdicts are pending. No runtime, migration, test,
CI, dependency, or Alembic environment file was changed by this planning
repair.

## Phase 3 gate

Phase 3 is authorized only if all exact-final-head reviewer receipts remain
PASS and the contract's base, prerequisites, sole migration head, frozen AUTH
Protocol, provider limitation, and allowed scope still match. Any drift invokes
the contract's stop-and-re-review rule.
