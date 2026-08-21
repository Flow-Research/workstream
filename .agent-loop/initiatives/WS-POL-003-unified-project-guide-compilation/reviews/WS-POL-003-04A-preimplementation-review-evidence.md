# WS-POL-003-04A Preimplementation Review Evidence

Date: 2026-08-21. Risk: L1. Runtime implementation: not started.

## Review target

- Stacked parent: `a1e2aaa3ba7e781d30ca7da09d3775af6659ec48`.
- First expanded contract: `0068c9ddb3a83561a0b56fa2a124067b58da08c2`.
- Remediated contract: `f2340679b6d4b08158ac1097c774b819b427e8d1`.
- PR #355 remained open, green, mergeable, and human-review gated at final
  contract review.
- Reviewers inspected the clean exact head against the stacked parent. This
  file records their read-only findings and verdicts; it does not claim that
  runtime implementation or protected-main delivery has occurred.

## Findings and resolution

| Finding | Resolution | Result |
|---|---|---|
| Hidden execution could impersonate the original Project Manager request | The public command now accepts only an already-authorized `attempt_id`; it cannot create, reconstruct, prepare, or consume human request authority. | Closed |
| Provider-side exactly-once behavior was unprovable | The contract now promises one committed application dispatch permit and at most one local runtime invocation; uncertain outcomes never redispatch. | Closed |
| Invalid output and transport uncertainty were indistinguishable | A bounded typed invalid-output exception is required; only observed invalid output terminalizes, while timeout, transport, configuration, cancellation, and unknown failure remain uncertain. | Closed |
| Partial provider output could acquire Pydantic defaults | Every result-envelope field must be explicitly present, while empty/null values remain valid only where the existing semantic validator permits them. | Closed |
| Agent version was not frozen in the provider context | The context now carries the server-owned expected version; the attempt manifest must match before fencing and the returned version must match before acceptance. | Closed |
| First-pass persistence unnecessarily rebuilt context | The exact frozen dispatched context is reused for first-pass acceptance/persistence; reconstruction is limited to accepted-not-persisted recovery. | Closed |
| Cross-deploy recovery could silently use a different manifest | Recovery must reproduce the exact ART/catalogue/runtime identity or fail closed without redispatch. | Closed |
| Live Celery redelivery and global legacy-call claims exceeded hidden scope | 04A adds no route, worker, or broker. Its reachability proof covers only the hidden candidate path; live cutover and broker proof remain POL-04B. | Closed |
| Bounded execution errors were undefined | The public port now exposes four safe codes only and preserves the existing durable attempt classification. | Closed |
| Coverage could hide weak changed files behind aggregate percentages | Local and hosted CI must enforce at least 90 percent for each materially changed production file, plus the unchanged 78 percent repository floor. | Closed |
| Atomic-state verification was not runnable | The command now supplies the exact stacked base, and the planned contract/CHUNK_MAP/STATUS/CURRENT_STATE projections are synchronized. | Closed |

## Exact-head reviewer verdicts

| Track | Verdict | Primary focus |
|---|---|---|
| Architecture | PASS | Execution-only boundary, immutable custody, context identity, transaction phases, fixed-service AUTH isolation |
| Simplicity and reuse | PASS | One command and state machine reusing POL-03B, ART material, and canonical catalogue factories |
| Security and authorization | PASS | No human impersonation, no caller authority, no provider credential exposure, no redispatch |
| QA and lifecycle | PASS | Valid, invalid, uncertain, accepted-recovery, concurrency, and forbidden-effect behavior |
| Test delta | PASS | Real PostgreSQL/production boundary proof, negative effects, call spies, and seeded-fault sensitivity |
| Senior engineering | PASS | Feasible module seams, bounded errors, short transactions, and stop conditions |
| CI and evidence | PASS | Runnable base-bound commands, exact per-file coverage, seven semantic lanes, and repository floor |
| Product and operations | PASS | Hidden-only behavior, honest uncertainty, and no false setup/policy/approval truth |
| Documentation and state | PASS | Atomic planned projections, Markdown links, stale wording, and clean exact-head diff |

No finding remained at `f2340679b6d4b08158ac1097c774b819b427e8d1`.
Implementation may start only while the stacked parent and reviewed contract
remain unchanged. Any stop condition in the contract returns the chunk to
planning and review before broader edits.

## Executed planning checks

```text
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_chunk_state_sync.py --base-ref a1e2aaa3ba7e781d30ca7da09d3775af6659ec48
```

No runtime, test, workflow, dependency, route, worker, provider, schema,
migration, push, pull request, or merge was created during this review.
