# Chunk Map: WS-AUTH-001 - Workstream Authorization Service

## Rule

Only one chunk may be active at a time. Do not start the next chunk until the
current chunk is implemented, verified, internally reviewed, externally
reviewed, merged by explicit human approval, followed by a memory update, and
stopped.

## Chunks

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-AUTH-001-PLAN` | Authorization Service Planning | L0 | Merged through PR #91 as `ad6d644` |
| `WS-AUTH-001-01` | Adopt Authorization Baseline And Repository Contracts | L1 | Merged through PR #93 as `772af1d` |
| `WS-AUTH-001-02` | Verified Issuer Token And JWKS Boundary | L1 | Merged through PR #107 as `060b780` |
| `WS-AUTH-001-03` | Legacy Actor Classification Preflight | L1 | Merged through PR #109 as `f06532e` |
| `WS-AUTH-001-04` | Request, Error, And API Control Foundation | L1 | Split before implementation into 04A and 04B |
| `WS-AUTH-001-04A` | Request And Error Context | L1 | Merged through PR #111 as `90c9a28` |
| `WS-AUTH-001-04B` | PostgreSQL Rate Controls | L1 | Merged through PR #113 as `05a63c8` |
| `WS-AUTH-001-05` | Authority Evidence And Idempotency Foundation | L1 | Split before implementation into 05A and 05B |
| `WS-AUTH-001-05A` | Shared Audit Ownership And Append-Only Authority Evidence | L1 | Merged through PR #115 as `8e1cde6` |
| `WS-AUTH-001-CAT` | Action And Resource Catalogue Reconciliation | L1 | Merged through PR #117 as `4c5d4fc` |
| `WS-AUTH-001-05B` | Authority Idempotency And Invalidation Foundation | L1 | Merged through PR #119 as `ad71c7e` |
| `WS-AUTH-001-06` | Canonical Actor Profile And Identity Link | L1 | Proposed |
| `WS-AUTH-001-07` | Authorization Kernel And Permission Registry | L1 | Proposed |
| `WS-AUTH-001-08` | Bootstrap And Administrative Role Grants | L1 | Proposed |
| `WS-AUTH-001-09` | Actor State, Identity Revocation, And Service Actors | L1 | Proposed |
| `WS-AUTH-001-10` | Project Qualification And Contributor Role Grants | L1 | Proposed |
| `WS-AUTH-001-11` | Project Identity, Guide, Source, And Visibility Cutover | L1 | Proposed |
| `WS-AUTH-001-12` | Project Policy And Setup Mutation Cutover | L1 | Proposed |
| `WS-AUTH-001-13` | Task Management And Assignment Cutover | L1 | Proposed |
| `WS-AUTH-001-14` | Submission, Checker, And Audit Visibility Cutover | L1 | Proposed |
| `WS-AUTH-001-15` | Remaining System Worker Cutover And Obsolete Authority Removal | L1 | Proposed |
| `WS-AUTH-001-16` | Conformance, Observability, And Live API Proof | L1 | Proposed |

## Dependency order

```text
WS-AUTH-001-PLAN
-> WS-AUTH-001-01
-> WS-AUTH-001-02
-> WS-AUTH-001-03
-> WS-AUTH-001-04A
-> WS-AUTH-001-04B
-> WS-AUTH-001-05A
-> WS-AUTH-001-CAT
-> WS-AUTH-001-05B
-> WS-AUTH-001-06
-> WS-AUTH-001-07
-> WS-AUTH-001-08
-> WS-AUTH-001-09
-> WS-AUTH-001-10
-> WS-AUTH-001-11
-> WS-AUTH-001-12
-> WS-AUTH-001-13
-> WS-AUTH-001-14
-> WS-AUTH-001-15
-> WS-AUTH-001-16
```

## Boundary notes

- Chunk 02 authenticates tokens but grants no product authority.
- Chunk 03 provides a supported classification gate before schema migration.
- Parent chunk 04 was split before implementation. Chunk 04A establishes
  request/correlation and additive error compatibility; chunk 04B later owns
  durable PostgreSQL rate controls and its migration.
- Parent chunk 05 was split before implementation. Chunk 05A owns shared audit
  schema/writer custody and append-only authority evidence; chunk 05B owns
  idempotency and typed invalidation orchestration.
- The docs-only catalogue reconciliation between 05A and 05B adopts a staged
  typed action/resource registry for future chunks without changing the merged
  permission/audit catalogue or starting runtime implementation.
- Chunk 06 establishes canonical actor resolution while preserving only the
  enumerated non-authoritative legacy workflow-eligibility consumers required
  for intermediate-release operability.
- Chunk 07 provides the single authorization engine before grant APIs.
- Chunks 08-10 establish local grant truth before product cutover.
- Chunks 11-15 migrate bounded complete product/system surfaces.
- Artifact upload, read, retention, release/delete, replication, integrity, and
  reconciliation remain mechanically owned by the artifact subsystem but must
  receive centralized AUTH decisions. Chunk 07 owns the permission-registry
  boundary, chunk 09 owns artifact service principals, the applicable 11-15
  resource cutovers attach enforcement, and chunk 16 proves no bypass remains.
- Chunk 16 proves the complete initiative; it does not backfill missing audit
  or idempotency evidence.
- `WS-POL-002-03` merged separately through PR #90 as `a7aa474`. This initiative
  does not own it; post-merge memory completed through PR #94. `WS-POL-002-04`
  remains inactive until the relevant project authorization cutover is complete
  and the user explicitly starts it.

## Stop condition

AUTH-03 post-merge memory merged through PR #110 as `1864867`. The user
explicitly started parent AUTH-04. Required plan review split it before runtime
implementation. AUTH-04A merged through PR #111 as `90c9a28`, and its
post-merge memory merged through PR #112 as `7749f54`. The user explicitly
started AUTH-04B. Its repaired contract passed at `b5dceb1`; bounded
implementation and all required internal review tracks passed, and PR #113
merged as `05a63c8` after Backend, Agent Gates, CodeRabbit, and explicit human
approval passed. AUTH-04B post-merge memory then merged through PR #114 as
`97cd0f5`, and the user explicitly started AUTH-05. Required plan review
rejected the combined contract before runtime edits and required 05A/05B.
The first 05A implementation review proved the original numeric ceiling
incompatible with readable typed/database privacy parity. Repaired 05A contract
review passed at `7cc6058`; the user subsequently replaced the line cap with
the semantic AUTH-05A boundary. Required reviews and checks passed, and explicit
human approval merged PR #115 as `8e1cde6` on 2026-07-14, followed by merged
post-merge memory. `WS-AUTH-001-CAT` then merged through PR #117 as `4c5d4fc`
after Backend, Agent Gates, CodeRabbit, and explicit human approval passed. The
CAT post-merge memory merged through PR #118 as `eba7e2b`; AUTH-05B then merged
through PR #119 as `ad71c7e` after required internal and external gates passed.
Do not start AUTH-06 or POL-002-04 automatically.
