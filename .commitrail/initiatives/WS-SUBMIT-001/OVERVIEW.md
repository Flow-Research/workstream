# WS-SUBMIT-001 — One-request submission and durable continuation

- Disposition: Planned
- Intent: implement the user-approved [specification](../../../docs/spec_submission_execution.md), preserving downstream authority and retained evidence.

The user authorized the complete specification on 11 November 2026. Completion
requires D01–D18, I01–I12, T1–T5 and evidence for A01–A35. This record does not
authorize merge or production deployment.

## Current boundary

[WS-SUBMIT-001-01](WS-SUBMIT-001-01.md) establishes exact command/source value
contracts. Database ownership and all new orchestration remain to implement.
The existing public flow stays active until coordinated cutover.

## Delivery sequence

1. Owner contracts/schema: exact identities, ART operation, TASK guard, accepted
   authority, PRE evidence and database constraints.
2. Streaming receipt, completion reconciliation, physical accounting and cleanup.
3. One-session PRE, trusted defaults, isolation and provider substitution proof.
4. Foreground T1–T4, exact replay and durable accepted receipt.
5. Worker T5, recovery and existing POST dispatch.
6. Single API/CLI/MCP mutation and truthful progress reads.
7. Image cardinality, readiness, migration/cutover and integrated proof.

Create each bounded record when work starts. Authorization covers this sequence;
do not repeat discovery or verification without a relevant changed assumption.

## Acceptance tracking

All integrated scenarios remain Planned. Contract unit tests do not complete
them. Final evidence must name the executed test/drill and proved boundary.

| Scenarios | Proof required | Disposition |
|---|---|---|
| A01–A03 | Public success and PRE failures | Planned |
| A04–A08 | Replay, concurrency, interruptions and unknown commit | Planned |
| A09–A13 | Worker recovery, authority and pending reads | Planned |
| A14–A18 | Cleanup races, protection, versions and physical charges | Planned |
| A19–A23 | Bounded ingress, framing, archives, identity and safe findings | Planned |
| A24–A30 | Substitution, runtime isolation/recovery, capacity and adapters | Planned |
| A31–A35 | Downstream behavior, migration, policy and clients | Planned |

## Configuration and reconciliation

C01–C07 remain unresolved as specified; fixtures are not approved deployment
defaults. Current Caddy allows 16 KiB total headers; target packet text permits
64 KiB each. Human-review execution remains unavailable in current main and is
not delivered by preserving its guards.

Initial main is `a4e485edea03db90c71189c51eac85cf4c3b1139`. The 14 commits after
the spec baseline change deployment/identity, not submission owners. At initial
intake, open PR #698 changed CLI preparation and #707 changed public access/profile
behavior. Reconcile affected surfaces without modifying their branches.

PR #707 merged during the first change. Reconciled current main `94334ccf4`,
including issuer-owned profile metadata, public Swagger and schema head 0068.
Its roadmap paragraph is preserved; no new submission behavior was introduced.

Real PostgreSQL, S3/MinIO and Smol proof is required where claimed. Request
missing live access when a concrete drill is prepared. Historical old-flow
drills cannot establish this implementation's completion.
