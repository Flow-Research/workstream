# Chunk Map: WS-ART-001 S3-Compatible Object Storage

Each chunk is one PR. No later chunk starts automatically.

| Chunk | Goal | Risk | Status |
|---|---|---:|---|
| `WS-ART-001-PLAN` | Original artifact planning. | L1 | Merged through PR #97 |
| `WS-ART-001-01` | Artifact domain and LocalStorage v1 foundation. | L1 | Merged through PR #101 |
| `WS-ART-001-OBJECT-STORAGE-AMENDMENT` | Make AWS S3 the v0.1 production provider with MinIO local/CI protocol proof; keep optional providers outside v0.1. | L1 | Merged through PR #120 as `4408256` |
| `WS-ART-001-02A1` | Install only ADR 0014's small typed external-service adapter/factory foundation without migrating a capability. | L1 | Merged through PR #127 as `f64a8e5` |
| `WS-ART-001-02A2` | Add bounded committed-source preparation and inactive scratch-cleanup mechanics without changing the active v1 port. | L1 | Merged through PR #129 as `9a04434` on 2026-07-16 |
| `WS-ART-001-02A3` | Replace ArtifactStore v1 with byte-only v2, activate API-startup and Celery Beat scratch cleanup, migrate schema/callers/factory, and remove `flow_node` in one atomic clean cut. | L1 | Merged through PR #141 as `a10d901` on 2026-07-18 |
| `WS-ART-001-02B1` | Implement the S3-compatible adapter, MinIO integration, and AWS S3 production profile. | L1 | Merged through PR #151 as `1b5422fc` on 2026-07-19 |
| `WS-ART-001-02C1` | Add the generic durable-byte admission ledger and durable put-attempt state foundation without provider execution. | L1 | Merged through PR #154 as `44f2467c` on 2026-07-19 |
| `WS-ART-001-02C2` | Add put resolution, verification publication, complete-object observation, immutable receipts, and PostgreSQL execution fencing without recovery attempts or routes. | L1 | Merged through PR #159 as `bc5e6a42` |
| `WS-ART-001-02C3` | Add the recovery-attempt model and exact idempotent source-job to retry-job chain without public or Operator routes. | L1 | Merged through PR #174 as `92b8a7aa` |
| `WS-ART-001-02D` | Add hidden Operator content/job/retry/recovery/audit APIs, canonical resource composition, and production-readiness checks while actions and provider profiles remain inactive. | L1 | Merged through PR #177 as `93c14181` |
| `WS-ART-001-03` | Original combined guide-source cutover. | L1 | Cancelled before implementation; no runtime changes |
| `WS-ART-001-PLAN2` | Reconcile guide and one-ZIP submission planning with bounded scratch, existing immutable admission/recovery, exact AUTH sequencing, and downstream ownership. | L1 | Planning-only successor proposed after cancellation |
| `WS-ART-001-03A` | Add hidden guide-source byte ingest through existing preparation, admission, verification, and publication. | L1 | Merged through PR #215 as `bb9082a7` |
| `WS-ART-001-03B1` | Add authoritative verified guide-source bindings and an exact setup-generation fence while fixed-service binding remains unavailable. | L1 | Proposed after 03A and AUTH-04A |
| `WS-ART-001-03B2` | Add fixed-reader verified materialization, artifact incidents, and canonical format detection in bounded ART scratch. | L1 | Proposed after 03B1 |
| `WS-ART-001-03B3A` | Add the isolated extraction framework, canonical records, and text/Markdown/JSON/CSV extractors. | L1 | Proposed after 03B2 |
| `WS-ART-001-03B3B1` | Approve the exact pinned complex-parser dependency allowlist and deterministic CI gate without installing packages or changing runtime code. | L1 | Proposed after 03B3A |
| `WS-ART-001-03B3B2` | Install only the approved PDF dependency and add bounded PDF text extraction. | L1 | Proposed after 03B3B1 approval |
| `WS-ART-001-03B3B3A` | Add shared bounded OOXML container/security capabilities without document extraction. | L1 | Proposed after 03B3B1 approval |
| `WS-ART-001-03B3B3B` | Add bounded DOCX extraction on the approved OOXML capability. | L1 | Proposed after 03B3B3A |
| `WS-ART-001-03B3B3C` | Add bounded PPTX extraction on the approved OOXML capability. | L1 | Proposed after 03B3B3A |
| `WS-ART-001-03B3B3D` | Add bounded XLSX extraction on the approved OOXML capability. | L1 | Proposed after 03B3B3A |
| `WS-ART-001-03B3B4` | Install only the approved image dependency and add PNG/JPEG/WebP structural metadata extraction. | L1 | Proposed after 03B3B1 approval |
| `WS-ART-001-03B4` | Feed only complete same-generation canonical extracted material into the existing Celery sufficiency pipeline. | L1 | Proposed after 03B3B2, 03B3B3B, 03B3B3C, 03B3B3D, and 03B3B4 |
| `WS-ART-001-03C` | Remove legacy guide-source identity and add exact same-generation setup continuation. | L1 | Proposed after 03B1-03B4 and AUTH-04B |
| `WS-ART-001-04A` | Accept one outer ZIP in bounded scratch, safely inspect its tree, normalize executable intent, produce canonical identities, and reject unchanged work before provider I/O. | L1 | Proposed after 03C and AUTH planned action registration |
| `WS-ART-001-04B` | Run mandatory platform and locked Project Guide pre-submit checks against the same scratch-bound tree and executable semantics without durable storage. | L1 | Proposed after 04A |
| `WS-ART-001-04C` | Reauthorize at durable intent, admit/verify the passing ZIP once, and publish one capacity-charged `ready` admission that may remain unbound. | L1 | Proposed after 04B; AUTH activation follows hidden completion |
| `WS-ART-001-05` | Freshly authorize and atomically consume one ready admission into one immutable Submission/binding, or terminally stale it on proven context drift. | L1 | Proposed after 04C and exact AUTH activation |
| `WS-ART-001-06A` | Persist checker input snapshots and materialize authorized immutable bytes with identical normalized executable semantics. | L1 | Proposed after 05 |
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
-> PLAN2 planning reconciliation
-> 03A guide-source byte ingest
-> AUTH activation for exact 03A actions
-> 03B1 authoritative guide binding/setup generation
-> 03B2 verified materialization/format detection
-> 03B3A isolated extraction framework/text formats
-> 03B3B1 pinned dependency approval and CI gate
-> 03B3B1 branches to:
   -> 03B3B2 approved PDF extractor
   -> 03B3B3A shared OOXML security capability
      -> 03B3B3B DOCX
      -> 03B3B3C PPTX
      -> 03B3B3D XLSX
   -> 03B3B4 approved image metadata
-> 03B4 same-generation Celery sufficiency integration only after 03B3B2,
   03B3B3B, 03B3B3C, 03B3B3D, and 03B3B4 complete
-> AUTH activation for exact 03B actions
-> 03C guide-source clean cut/continuation
-> AUTH planned registration of `artifact.submission_bundle.prepare`
-> 04A one-ZIP scratch intake/inspection/manifest/change gate
-> 04B scratch-bound platform/project pre-submit checks
-> 04C one-time immutable admission/verification
-> AUTH activation of exact complete contributor surface
-> 05 submission cutover
-> 06A checker input/materialization
-> 06B checker output/post-submit routing
-> 07 live proof
```

`FN-ART-002` is deferred and is not in this dependency graph. R2 is also
deferred. It has no active chunk, runtime profile, credential service, or
configuration value in v0.1.
`ReviewPacketManifest` and `ReviewEvidenceArtifact` remain owned by WS-REV.
Physical deletion, temporary provider retention, candidate object storage, and
semantic search require separate approved initiatives.

## Cross-Initiative Handoffs

The exact authorization sequence and stop conditions are recorded in
`AUTH_HANDOFF.md`.

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
  paths, or concrete adapters. REV also owns reviewer decisions and
  note/findings for
  the exact `Submission`; `needs_revision` authorizes a later contributor ZIP
  but contains no reviewer-uploaded artifact.
- A future optional contribution-evidence projection requires separately
  approved ART-owned read/write capabilities and AUTH action activation. Core
  ContributionRecord creation makes no ART capability/provider call and is not
  gated by that projection. No contribution capability is implied by this chunk
  map.
- Cross-initiative terminology must use ART's canonical `resource_type`,
  `resource_id`, and `logical_role`, or define an explicit integration mapping;
  product initiatives must not create a second binding vocabulary implicitly.
- The existing immutable `Submission` row is the version aggregate. TASK/REV
  jointly own the exact `needs_revision` response relation and indexed
  latest/current/accepted access; no initiative creates a competing
  `SubmissionVersion` table.
- Reviewer and delivery streams consume an ART-owned integrity-checking read
  capability that recomputes full SHA-256 and byte count. ART does not own the
  review decision, ContributionRecord, compensation, reputation, or delivery
  lifecycle that consumes that capability.

## Checkpoint Before Checker Expansion

Do not resume checker feature expansion until `WS-ART-001-06B` proves pre-submit
evidence and post-submit execution name the same archive identity,
semantic-manifest hash, verified admission, and exact binding.
