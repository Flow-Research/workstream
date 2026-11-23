# WS-SUBMIT-001 — Submission execution completion checklist

- Disposition: Planned
- Target: the complete [submission execution specification](../../../docs/spec_submission_execution.md).
- Delivery: one PR, #708, with focused commits; no merge request before complete verification.

## Implemented on this branch

Checked items describe implementation with focused proof. They do not mean the
complete acceptance matrix or deployment is qualified. Detailed runs and their
limits are in [the change record](WS-SUBMIT-001-01.md).

- [x] Exact intake/source identities, durable custody, leases and physical byte reservations.
- [x] Streaming Local/MinIO source upload and source-bound PRE orchestration.
- [x] Atomic T4 acceptance: pending task custody, accepted receipt and durable finalization event.
- [x] T5 formal Submission/binding/POST dispatch through existing owners, with replay and rollback tests.
- [x] Public raw-ZIP API and corresponding CLI/MCP submission/progress contracts.
- [x] One-image-per-phase policy guards and retained-policy refusal.
- [x] Revision expiry and assignment invalidation serialize with acceptance; accepted input remains protected.
- [x] Pending-revision protection prevents dispatch against the older Submission.
- [x] Cleanup claim, retention barriers, exact-generation deletion and confirmed charge release owners.
- [x] Historical cap fixture no longer depends on the old writer; capture, restore/recovery and neighboring upgrade controls passed.

Recent focused evidence includes atomic invalidation (`8a854f7a6`), public
ZIP/T5 lineage (`168e5268f`), and policy-error translation (`d31a45773`). The
last change passed seven PostgreSQL cases and 92 boundary checks. These are
bounded results, not full-head qualification.

## Remaining work, in execution order

| Order | Required outcome | Concrete finishing evidence |
| --- | --- | --- |
| 1 | Integrate production source cleanup scheduling/startup and uncertain/unsealed reconciliation | Real worker callers of the cleanup owner; restart and repeated sweeps; interrupted multipart and lost acknowledgements; accepted/stalled source survives; confirmed cleanup releases charge once. |
| 2 | Remove superseded preparation/submission writers and remaining consumers | Trace all remaining callers, preserve their distinct authority/history contracts, then delete obsolete implementation. Current T5 `create_accepted` remains. |
| 3 | Complete native/runtime/provider and resource qualification | Actual Smol one-session/isolation proof; representative maxima, cold paths, concurrency and timing measurements; applicable AWS exact-version/uncertain multipart proof. Portable/MinIO evidence is insufficient for these claims. |
| 4 | Execute final full-system verification and close the acceptance matrix | Full backend lanes, CLI/MCP contracts and CI at the final head; every A01–A35 row linked to an executed, scope-matching result. Fix actual failures without weakening requirements. |
| 5 | Reconcile configuration and delivery documentation | Resolve C01–C07 using measured/approved values; update affected roadmap/overview/index and local spreadsheet exports; preserve the distinction between implemented, exposed and deployed. |

The concrete next runtime gap is order 1: the ART cleanup execution and provider
factory exist, but the current production worker tree has no caller. Further
optional test migration must not displace closing this integration.

## Acceptance evidence still to close

No row below is declared fully complete merely because some related tests pass.
This is the final qualification queue, not a claim that all listed code is absent.

| IDs | Existing implementation/focused evidence | Required closure |
| --- | --- | --- |
| A01–A03 | Public ZIP flow, default/project PRE and formal finalization tests | Complete API/CLI journey with required real runtime and POST evidence. |
| A04–A08 | Metadata/body replay, competing custody, interruption and T4 uncertainty tests | Reconcile exact cases and execute integrated final-head failure/retry matrix. |
| A09–A13 | T5 rollback/redelivery, accepted authority, pending reads and old-POST guard | Real worker crash/broker-unavailable drill and final-head reconciliation. |
| A14–A18 | Cleanup lock/retention/charge owners and Local/MinIO provider tests | Production sweeps, accepted-source survival, AWS versions and uncertain multipart ownership. |
| A19–A23 | Streaming/framing, safe archives, semantic identity and bounded findings code/tests | Measured permitted maxima/slow-provider memory bounds and complete safety matrix. |
| A24–A30 | Source/result/fence contracts and runtime/capacity/substitution tests | Actual native isolation/failure/cleanup, multiple replicas/nodes, saturation and adapter qualification. |
| A31–A32 | Existing governed POST/revision/acceptance owners preserved with focused journeys | Final combined downstream tests, exact ContributionRecord/award facts, both review branches. |
| A33–A35 | Retained migrations, cardinality guards and API/CLI/MCP cutover | Finish old-writer retirement and full current-head migration/client convergence proof. |

## Configuration and external evidence

C01–C07 remain open until individually reconciled with the specification and
actual deployment evidence. Test-only leases/profiles are not approved defaults.
Current local inspection found no `/dev/kvm` or `smol` executable, so this host
cannot currently provide the required native Smol qualification. AWS source
qualification remains separate from MinIO and existing SHA-object activation.
Request only concrete missing access or decisions after the corresponding drill
and proposed values are prepared.

The full goal includes D01–D18, I01–I12, T1–T5 and A01–A35. A partial green
suite, fixture capture, review approval or a single commit does not complete it.
