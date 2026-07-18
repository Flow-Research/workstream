# External Review Response: WS-REV-001-PLAN

## Pull Request

PR #128: `https://github.com/Flow-Research/workstream/pull/128`

Reviewed branch head before repair:
`e6417c37f8aef4ae4556cacb0dbe84bc481e45a4`

Reviewed repaired code SHA:
`86ee0a5e263ac306b3bf195a9fb9043aa5439416`

Current reviewed normative SHA:
`12a781b2c4e8e8bb3378e3c4cb4f7c32ac9ba5be`

Current trusted main SHA:
`299363af5d9e8a68bcc9b17457188048483caeed`

## Comments Addressed

| Thread | Disposition | Repair |
|---|---|---|
| `PRRT_kwDOSwL_U86RL5kg` | Fixed | Added the exact WS-IMP Markdown/PDF archival pair to chunk 01 allowed files; existing checksum/provenance acceptance criteria now have matching scope. |
| `PRRT_kwDOSwL_U86RL5km` | Fixed | Clarified that the WS-CON compensation-policy persistence contract must be merged with its exact lease-freeze FK/field types before REV-03 activation. |
| `PRRT_kwDOSwL_U86RL5kq` | Fixed | Expanded REV-13's final conformance command to include lifecycle-control, task, checker, outbox, audit, and configuration tests. |
| `PRRT_kwDOSwL_U86RaIER` | Fixed | Added task/app composition tests and task-router/checker-worker/composition lint paths to REV-05 verification and allowed test scope. |
| `PRRT_kwDOSwL_U86RaIEX` | Fixed | Corrected `later-admitted` compound-modifier wording. |
| `PRRT_kwDOSwL_U86RaIEa` | Fixed | Defined chain ownership as the canonical contributor on the exact TaskAssignment associated with a Submission in the requested chain. |
| `PRRT_kwDOSwL_U86RaIEc` | Fixed | Added `test_app.py` OpenAPI path-inventory verification to REV-07 and REV-09A so hidden lifecycle routes are proved absent before activation. |
| `PRRT_kwDOSwL_U86RaIEi` | Fixed | Expanded the REV-13 90 percent coverage gate from the lifecycle-control router to the complete lifecycle-control package. |
| `PRRT_kwDOSwL_U86Rr721` | Fixed | Made `delivery_draining` reachable, moved the full zero-obligation guard to `disabled`, added a CON-derived immutable root cutoff and mandatory writer fencing, restricted the drain to pre-cutoff completion work, and specified audited same-root claim recovery for denied dispatch. |
| `PRRT_kwDOSwL_U86Ryg7Z` | Fixed | Classified Flow Node wording as hash-verified byte-preserved archival evidence, stated canonical adoption remains incomplete, and assigned future AWS S3/MinIO active-contract creation to REV-01 without editing the source. |
| `PRRT_kwDOSwL_U86Ryg7i` | Fixed | Rendered WS-XINT PR `#139` as inline code so Markdown cannot parse it as a malformed heading. |

## Comments Deferred

None.

## Internal Re-Review

| Tracks | Agent | Result |
|---|---|---|
| Senior engineering, architecture, reuse/dedup | `/root/final_art_senior_review` | PASS |
| QA/test, product/ops | `/root/final_art_qa_review` | PASS |
| Security/auth, docs, CI integrity | `/root/final_art_security_review` | PASS AFTER FIXES |

The first re-review rejected `test_api_contract_e2e.py` as insufficient OpenAPI
proof. REV-07/09A were repaired to allow, run, and lint the established
`test_app.py` application path inventory before the final PASS.

The 2026-07-17 refresh review first exposed an unreachable delivery-drain phase.
Internal review then hardened the repair through four bounded cycles: durable
pre-cutoff lineage, mandatory fence coverage for every CON obligation writer,
exact command-class alignment, auditable already-claimed denial recovery, and
matching high-level architecture summaries. Exact snapshot
`86ee0a5e263ac306b3bf195a9fb9043aa5439416` passed all required tracks.

## Human Decisions Needed

None beyond the existing explicit human merge approval for PR #128 and the
separate post-merge start decision for `WS-REV-001-01`.

## Commands Rerun

```text
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
sha256sum -c docs/reference_specs/SHA256SUMS
python3 scripts/check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
cd backend && .venv/bin/python -m pytest -q tests/test_app.py
```

All applicable REV commands passed after the earlier evidence-only binding. The
OpenAPI inventory suite passed 4 tests. At that time the repository-wide
loop-memory check reported AUTH-owned stale status. Merged AUTH PR #140 repaired
that trusted-main state, and the current reconciliation rerun passes; the earlier
failure is historical rather than a remaining gate.

## Remaining Risks

- Reviewer-specific ART read/intake port ownership remains a future ART-owned
  fail-closed gate at REV-07.
- CON must merge the obligation-writer, dispatch, and callback fence hooks,
  monotonic root ordinal, and drain-cutoff/observation port before REV-12A.
- This response changes planning contracts only; every named future test and
  coverage command must exist and pass when its owning implementation chunk is
  activated.

## PR #140 Reconciliation Refresh - 2026-07-17

PR #128 was rebased onto trusted main
`d541521790a0441cfd2193f466e00ef81248ec31`. Exact normative snapshot
`7a76da2a79243cf61936d3bc7cf2606a82f0b5d8` passed all nine required internal
tracks after repair of AUTH dependency, PREP, transaction, and cutover-ownership
findings. Publication head `9ee090b9f44ec7c81be5a0a112898be6386b4aba`
then passed both agent-gate jobs and CodeRabbit while the backend suite continued.

The thread-aware GitHub query reported nine total review threads and zero
unresolved threads. CodeRabbit's only remaining comment was a non-blocking PR-
description warning: the body contained the correct evidence but did not use all
repository template headings. The evidence-only trust-bundle refresh now adds
Human-Approved Intent, Why/Design/Alternatives, allowed-file scope, product
behavior, commands/results, acceptance proof, test delta, the exact nine-track
reviewer table, external review, CI integrity, remaining risks, follow-up work,
and human merge ownership. No normative plan, chunk contract, runtime, workflow,
or test threshold changed.

Final publication-head CodeRabbit and GitHub checks must rerun after this
description-only commit. Explicit human approval remains required to merge.

## AUTH-09A PR #132 Reconciliation Refresh - 2026-07-17

PR #128 was rebased cleanly onto trusted main
`299363af5d9e8a68bcc9b17457188048483caeed`. Exact normative snapshot
`12a781b2c4e8e8bb3378e3c4cb4f7c32ac9ba5be` passed all nine required internal
tracks after current catalogue/migration/service-identity reconciliation and
repair of the guide identity/activation-sequence wording.

The plan now records 74 PermissionIds and 65 ActionIds: 9 active and 56 planned.
AUTH-09A supplies migration `0023` and a seven-identity/eleven-membership ART
foundation but no provisioning, service-token admission, action activation, or
REV identity. All 24 REV dependencies remain unavailable; each of REV's six
service identities remains separately gated through exact extensions,
AUTH-09B provisioning, and AUTH-09E admission.

The guide rule is now exact across active planning: compare the prior
Submission's stamped identity/activation sequence with the internally
consistent Project Guide active during preparation. Exact match keeps; a valid
difference rebases forward or backward; invalid or unsafe context blocks. Task
Context returns the frozen preparation, and the reviewer never rebases.

CodeRabbit's two findings on the first AUTH-09A publication were repaired at
`12a781b`: archival Flow Node wording is now clearly separated from future
active provider adoption, and the PR `#139` continuation is valid Markdown.

No current external result is claimed for the rebased head. Agent Gates,
Backend, CodeRabbit, and thread state must be refreshed after force-push before
the PR is reported merge-ready. Explicit human merge approval remains required.
