# Chunk Map: WS-ART-001 S3-Compatible Object Storage

Each chunk is one PR. No later chunk starts automatically.

| Chunk | Goal | Risk | Status |
|---|---|---:|---|
| `WS-ART-001-PLAN` | Original artifact planning. | L1 | Merged through PR #97 |
| `WS-ART-001-01` | Artifact domain and LocalStorage v1 foundation. | L1 | Merged through PR #101 |
| `WS-ART-001-OBJECT-STORAGE-AMENDMENT` | Make AWS S3 the v0.1 production provider with MinIO local/CI protocol proof; keep optional providers outside v0.1. | L1 | Merged through PR #120 as `4408256` |
| `WS-ART-001-02A1` | Install only ADR 0014's small typed external-service adapter/factory foundation without migrating a capability. | L1 | Merged through PR #127 as `f64a8e5` |
| `WS-ART-001-02A2` | Add bounded committed-source preparation and inactive scratch-cleanup mechanics without changing the active v1 port. | L1 | Merged through PR #129 as `9a04434` on 2026-07-16 |
| `WS-ART-001-02A3` | Replace ArtifactStore v1 with byte-only v2, activate API-startup and Celery Beat scratch cleanup, migrate schema/callers/factory, and remove `flow_node` in one atomic clean cut. | L1 | Internal review and deterministic evidence passed; external checks pending |
| `WS-ART-001-02B1` | Implement the S3-compatible adapter, MinIO integration, and AWS S3 production profile. | L1 | Proposed after 02A3 |
| `WS-ART-001-02C1` | Add the generic durable-byte admission ledger and durable put-attempt state foundation without provider execution. | L1 | Proposed after 02B1 |
| `WS-ART-001-02C2` | Add put resolution, verification publication, complete-object observation, immutable receipts, and PostgreSQL execution fencing without recovery attempts or routes. | L1 | Proposed after 02C1 |
| `WS-ART-001-02C3` | Add the recovery-attempt model and exact idempotent source-job to retry-job chain without public or Operator routes. | L1 | Proposed after 02C2 |
| `WS-ART-001-02D` | Add hidden Operator content/job/retry/recovery/audit APIs, canonical resource composition, and production-readiness checks while actions and provider profiles remain inactive. | L1 | Proposed after 02C3, AUTH-09E, and `WS-AUTH-001-ART-CUSTODY` |
| `WS-ART-001-03` | Store and bind guide-source bytes; add same-snapshot setup recovery through the authorized artifact reader. | L1 | Proposed after 02D |
| `WS-ART-001-04A` | Add task-scoped upload sessions/items, trusted archive inspection, independent verification, immutable sealing, and artifact-set manifests. | L1 | Proposed after 03 |
| `WS-ART-001-04B` | Execute authoritative pre-submit against sealed artifact sets and persist exact admissions with bounded infrastructure continuation. | L1 | Proposed after 04A |
| `WS-ART-001-05` | Atomically bind admitted artifact sets to submissions and remove legacy URI/hash/finalization contracts. | L1 | Proposed after 04B |
| `WS-ART-001-06A` | Persist checker input snapshots and materialize authorized immutable bytes into bounded checker workspaces. | L1 | Proposed after 05 |
| `WS-ART-001-06B` | Ingest checker logs/outputs as artifacts, persist checker completion facts, and preserve existing checker-owned routing without creating review aggregates. | L1 | Proposed after 06A |
| `WS-ART-001-07` | Prove Local/MinIO plus AWS S3 readiness, Operator recovery, and exact-byte guide/pre/post-submit behavior through real APIs. | L1 | Proposed after 06B |

## Dependency Order

```text
OBJECT-STORAGE-AMENDMENT
-> 02A1 shared adapter/factory foundation
-> 02A2 committed-source preparation and LocalStorage internals
-> 02A3 ArtifactStore v2/LocalStorage/schema clean cut
-> 02B1 S3-compatible adapter, MinIO, and AWS profile
-> 02C1 generic durable-byte admission and put-attempt foundation
-> 02C2 put resolution, verification publication, and fencing
-> 02C3 recovery attempt and idempotency chain
-> 02D Operator and production readiness
-> 03 guide source cutover
-> 04A upload/inspection/sealing
-> 04B pre-submit admission and outage continuation
-> 05 submission cutover
-> 06A checker input/materialization
-> 06B checker output/post-submit routing
-> 07 live proof
```

`FN-ART-002` is deferred and is not in this dependency graph. R2 is also
deferred. It has no active chunk, runtime profile, credential service, or
configuration value in v0.1.
`ReviewPacketManifest` and `ReviewEvidenceArtifact` remain owned by WS-REV.
Physical deletion and semantic search require separate approved initiatives.

## Cross-Initiative Handoffs

- Artifact actions follow AUTH planned registration -> hidden ART behavior and
  canonical resource composition -> AUTH evaluator integration and activation.
  `WS-AUTH-001-ART-CUSTODY` first transfers the 25 current ART actions to eight
  exact AUTH activation custodians without changing mappings or availability.
  Protected service commands first pass AUTH-09E. They consume canonical
  `ActorProfile.id`, closed `ActionId` and `PermissionId` catalogues, and exact
  fixed service matrix rows. ART never changes action
  availability. Provider idempotency labels and persisted role snapshots are
  provenance, not authority.
- WS-REV owns `ReviewPacketManifest` and `ReviewEvidenceArtifact`. Review code
  receives verified Workstream `ArtifactBinding` IDs through a narrow
  review-facing capability; it must not receive provider references, scratch
  paths, or concrete adapters.
- A future optional contribution-evidence projection requires separately
  approved ART-owned read/write capabilities and AUTH action activation. Core
  ContributionRecord creation makes no ART capability/provider call and is not
  gated by that projection. No contribution capability is implied by this chunk
  map.
- Cross-initiative terminology must use ART's canonical `resource_type`,
  `resource_id`, and `logical_role`, or define an explicit integration mapping;
  product initiatives must not create a second binding vocabulary implicitly.

## Checkpoint Before Checker Expansion

Do not resume checker feature expansion until `WS-ART-001-06B` proves pre-submit
and post-submit consume the same immutable artifact-set commitment.
