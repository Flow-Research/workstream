# WS-POL-003-03B Implementation Review Evidence

Date: 2026-08-21. Risk: L1. Outcome: ready for exact-head review.

## Review target and boundary

- Authoritative base: `c716fa424c1a86bda9e0f85c77c307fa07172bca`.
- Phase 3 implementation head: `3403860ac4022fb9305fdea96ce62f4ec8289dbe`.
- Phase 4 remediation head: `fd4364a76a45610750d1132c9e1912d14e8741a8`.
- Final planning head: `400d55f004cc906bec6ae1c8e1cad5f3adfd031c`.
- Atomic completion-projection and Docker-test head:
  `5062b64d02a0898fb38fd55fbdf08f147f143593`.
- Scope remains the hidden POL-03B persistence boundary. It adds no provider
  call, worker dispatch, outbox message, route, public Projects API, setup
  cutover, approval, policy projection, review, contribution, or economic
  effect.

Evidence below is labelled as **executed**, **inspected**, **hosted-only**, or
**deferred**. A test name or narrative claim is not treated as proof by itself.

## Findings closed during Phase 4

| Finding | Resolution | Proof status |
|---|---|---|
| Seven stale human/worker authorization phrases | Replaced with the exact principal, actor-kind, identity-link, grant, fixed-service, action, permission, resource, and state language enforced by AUTH | Executed stale-authorization scanner PASS |
| Two pre-existing repository test files were touched outside the contract | Restored `test_repository_attempts.py` and `test_repository_persistence.py` byte-for-byte to the base; new proof lives only in admitted files | Executed `git diff --quiet` against both files |
| Digest proof could miss individual inputs | Real PostgreSQL now recomputes the SQL and Python facts digest while mutating all 24 request fields, then mutates all six authority inputs independently; each result remains byte-identical across implementations and differs from the base | Executed in `test_sql_and_python_request_digests_are_byte_identical` |
| A trigger could accept stale digest evidence even if helpers agree | Direct SQL changes the stored facts digest and authority digest separately; both trigger paths reject. Null and non-null predecessor inputs are also covered. | Executed real-PostgreSQL trigger tests |
| Request rollback did not directly assert the consumed AUTH event disappeared | An injected request-operation insert failure now proves attempt, request receipt, and matching allowed audit-event counts remain `(0, 0, 0)` | Executed in `test_request_failure_rolls_back_attempt_and_authority_event` |
| Exact-file coverage could be hidden by package averaging | Added meaningful missing-row, replay, immutable-custody, recovery, and error-path tests until each named changed surface exceeded 90 percent | Executed branch coverage: repository 94.31% at Phase 3 and 96.24% in the final semantic aggregate |
| Completion projections were not atomic | Contract, CHUNK_MAP, STATUS, and CURRENT_STATE were changed in one commit and distinguish the on-merge outcome from protected-main truth | Executed chunk-state gate plus 18 regression tests |

## Requirement, risk, test, and evidence

| Requirement | Main escape risk | Discriminating proof | Evidence custody |
|---|---|---|---|
| Atomic authorized request | AUTH event, attempt, or receipt commits alone | Inject failure after AUTH consumption and query all three row counts | Executed, real PostgreSQL: `(0, 0, 0)` after rollback |
| Exact idempotency | Concurrent roots create duplicate request or final custody | Two independent sessions race request and finalization | Executed, real PostgreSQL: one attempt/event/receipt and one compilation/final event |
| SQL/Python digest parity | Trigger and application hash different preimages | Mutate 24 facts fields and six authority inputs one at a time | Executed, real PostgreSQL; all mutations discriminated |
| Immutable audit binding | Borrowed event or changed actor/action/resource satisfies custody | Direct SQL substitutions plus immutable update/delete/truncate probes | Executed, real PostgreSQL; owning trigger/constraint rejects |
| Committed pre-I/O fence | External work starts before durable uncertain state | Fresh subprocess reads the committed uncertain row and key; provider sentinel remains zero | Executed; second process observed exact row before any provider call |
| No redispatch from uncertainty | Restart duplicates a one-shot provider call | Fresh session invokes recovery with a fail-on-access authority/provider sentinel | Executed; returns `provider_outcome_unresolved`, sentinel calls `0` |
| Atomic final persistence | Final AUTH event, compilation, or attempt transition commits alone | Inject failure after final authority consumption and assert rollback, then retry | Executed, real PostgreSQL; no partial rows and accepted result remains recoverable |
| Closed recovery/status mapping | Unknown or repeated state is misreported | Exercise reserved, uncertain, accepted, persisted, invalid, repeated, and illegal transitions | Executed; only the closed classifications are returned |
| No later-product effects | Hidden persistence accidentally dispatches or projects | Import/call sentinel and before/after downstream-table counts | Executed and inspected; zero provider/outbox/setup/policy/approval/checker/contribution effects |
| Migration custody | 0008 drifts from the sole head or can remove governed evidence | Baseline/current/no-op/unsupported-head tests; update/delete/truncate and guarded downgrade | Executed in digest-pinned PostgreSQL 16 |
| Test sensitivity | Correct-looking tests pass after a key guard is removed | Six temporary seeded defects, restored before commit | Executed; all six mutants killed and clean code passed afterward |

## Seeded-fault sensitivity

Each mutation was applied temporarily to one bounded working copy, its exact
discriminating test was required to fail, the mutation was restored, and the
same test was required to pass. No mutant was committed.

| Fault family | Seeded defect | Required observation | Result |
|---|---|---|---|
| Authorization | Skip or bypass final AUTH consumption | Final-authorization integration test fails before persistence | Killed, restored, PASS |
| Digest | Remove/change a request digest input | SQL/Python per-field parity or custody trigger test fails | Killed, restored, PASS |
| Locking/idempotency | Remove the locking/replay convergence guard | Independent-session race produces a failing cardinality assertion | Killed, restored, PASS |
| Rollback atomicity | Allow a request event to survive operation failure | Exact `(attempt, operation, event)` count assertion fails | Killed, restored, PASS |
| Status mapping | Map an uncertain/recovery state to the wrong public classification | Closed recovery matrix test fails | Killed, restored, PASS |
| No redispatch | Permit uncertain recovery to touch authority/provider | Zero-call sentinel raises immediately | Killed, restored, PASS |

## Focused and structural verification

Executed before the completion projection; production code did not change
afterward:

- Focused guide-compilation/AUTH suite: 114 passed against real PostgreSQL.
- Migration, authorization-boundary, lane-inventory, behavior-ownership, and
  test-structure suite: 184 passed.
- Package branch coverage: 96.47 percent.
- Named changed surfaces: contracts 97.94 percent, models 100 percent,
  repository 94.31 percent, service 97.44 percent, and validation 92.59 percent.
- Ruff, migration head parity, Markdown links, stale Workstream wording, stale
  authorization wording, stale artifact contracts, and diff integrity passed.

The exact completion-projection head also passed:

```text
python3 scripts/check_chunk_state_sync.py \
  --base-ref c716fa424c1a86bda9e0f85c77c307fa07172bca
python3 -m unittest -v scripts.test_chunk_state_sync
```

The first command passed and all 18 regression tests passed.

## Canonical Docker and semantic-lane proof

The canonical run used native Linux, Python 3.12.13, and backend image manifest
`sha256:6abac3af7fdb493c334738a4adc183c2c81489637df9da5634f79661ab71133f`.
Only Git 2.39.5 was added to the ephemeral test container so the repository's
head-binding runner could execute. The source mount was read-only and bound to
head `5062b64d02a0898fb38fd55fbdf08f147f143593`.

Services were real and digest pinned:

- PostgreSQL 16:
  `sha256:33f923b05f64ca54ac4401c01126a6b92afe839a0aa0a52bc5aeb5cc958e5f20`.
- Redis 7:
  `sha256:b2b95679e3b46fb51864949ed25ea976fc3a6bcc00a40a1bc00d568cb2822e50`.
- MinIO:
  `sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`.

Each canonical lane command ran exactly once, sequentially, in a fresh evidence
root. The independent merger and validator accepted the common manifest and
exact custody of all 4,107 nodes.

| Lane | Collected | Completed | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| shared_foundations_a | 1,540 | 1,540 | 0 | 0 | 0 | 187.027 |
| shared_foundations_b | 1,503 | 1,503 | 0 | 0 | 0 | 193.995 |
| schema_contracts_a | 73 | 73 | 0 | 0 | 0 | 27.728 |
| schema_contracts_b | 3 | 3 | 0 | 0 | 0 | 9.492 |
| schema_contracts_c | 7 | 7 | 0 | 0 | 0 | 16.654 |
| project_lifecycle | 526 | 526 | 0 | 0 | 0 | 308.267 |
| task_lifecycle | 455 | 455 | 0 | 0 | 0 | 262.958 |

There were no duplicate completions, unexplained skips, deselections,
timeouts, cancellations, interruptions, or retries. Each isolation receipt
reported database and MinIO cleanup complete.

Combined semantic coverage passed every enforced local floor:

- Repository: 91.16 percent, floor 78 percent.
- Artifact foundation: 90.14 percent, floor 90 percent.
- Artifact module: 90.11 percent, floor 90 percent.
- Cancellation and file locks: 95.56 percent, floor 90 percent.
- Artifact interfaces: 99.69 percent, floor 90 percent.
- External-service interface: 100 percent, floor 90 percent.
- Final guide-compilation package: contracts 98.90 percent, models 100 percent,
  repository 96.24 percent, service 98.46 percent, validation 95.24 percent.

### Invalid exploratory attempts

Three earlier attempts are recorded only as failed operational evidence and
are not counted as product passes:

1. An operator launched local lane runners in parallel against one shared
   PostgreSQL/MinIO namespace. The shared-foundation bucket collided and an
   isolation self-test observed another runner's database cleanup. This was
   operator-induced parallel isolation interference.
2. An all-lane local invocation also starts lanes concurrently and reproduced
   the same unsupported shared-MinIO collision. It was stopped and discarded.
3. A host macOS lane completed custody but failed Linux `/proc`-dependent
   artifact tests. The contract requires Docker/Linux for this platform. The
   first Docker preflight then rejected non-loopback service names before test
   execution, as designed; the final container namespace used loopback for
   both providers.

None of these attempts was retried into or merged with the canonical green
bundle. Exact residual databases, roles, and buckets were ownership-checked
and removed before the fresh Linux run.

## Final reviewer verdicts

All reviewer tracks must run `python3 scripts/review_target.py` at start and
end against the exact clean final evidence head. This section is intentionally
pending until those read-only reviews complete.

| Track | Verdict | Final focus |
|---|---|---|
| Architecture | PENDING | Owner boundaries, transaction placement, hidden composition, no competing protocol |
| Reuse/dedup | PENDING | Reuse of AUTH-12I/POL-03A and absence of generic provider/operation frameworks |
| Security/authorization | PENDING | Substitution, replay, revocation, audit custody, rollback, and bounded data |
| QA | PENDING | Real PostgreSQL, concurrency, recovery, exact effects, and false-green probes |
| Test delta | PENDING | Meaningful assertions, mutation sensitivity, coverage, stable inventory |
| Senior engineering | PENDING | Simplicity, failure taxonomy, cancellation, transaction/session safety |
| CI integrity | PENDING | Exact lane custody, floors, Docker identity, no masked retry or gate weakening |
| Product/operations | PENDING | Operator-visible uncertainty and absence of later-product truth |
| Documentation | PENDING | Current-main accuracy, terms, links, commands, and deferred ownership |

## Residual and deferred proof

- **Hosted-only:** GitHub Actions, branch protection, required checks, and the
  exact pushed SHA cannot run before Phase 5 publication. Local Docker proof
  uses the same lane and evidence validators but does not claim hosted status.
- **Deferred to POL-04A:** actual provider execution, Celery delivery/redelivery,
  reconcile-by-key observation, and private setup-service consumption.
- **Deferred to POL-04B and later:** public/live setup cutover, approvals,
  policy projection, review, contribution, reputation, compensation, and
  settlement behavior.
- The conservative uncertain state can strand work when it is unknown whether
  a provider call began. It deliberately refuses redispatch until POL-04A
  proves a same-key observation contract.

Phase 5 publication is authorized only after every final reviewer returns PASS,
the final head is clean, and all affected deterministic gates still pass. This
document does not authorize push, pull-request creation, merge, or POL-04A.
