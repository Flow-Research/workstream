# Work Queue

## In Progress

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-AUTH-001-09E` | Fixed Service Runtime Admission | L1 | Runtime, focused evidence, and all nine internal tracks pass after repair; hosted Backend CI and human review remain |

Live post-merge state remains read from signed `automation/loop-memory`
output. This authored queue records the separately approved parallel chunks.

## Planned Next

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-QUAL-001-01B2` | Baseline Evidence And CI Ratchet | L1 | Paused for AUTH priority; no valid replacement baseline yet |
| `WS-QUAL-001-02` | Project Service Coverage | L1 | Inactive until 01B2 merge/memory plus explicit user start |
| `WS-POL-002-04` | Locked Runtime Execution And Routing Hardening | L1 | Inactive pending relevant authorization proof and a separate explicit user start |
| `WS-ART-001-02C2` | Verification Publication And Fencing | L1 | 02C1 merged; inactive until explicit user start |
| `WS-ART-001-02C3` | Recovery Attempt And Idempotency Chain | L1 | Inactive until 02C2 merge and explicit user start |
| `WS-ART-001-02D` | Operator Artifact Operations And AWS Readiness | L1 | Inactive until 02C3 and exact AUTH prerequisites |

## Completed

| Chunk | Title | Risk | Status |
|---|---|---:|---|
| `WS-ART-001-02C1` | Admission And Put-Attempt Foundation | L1 | Merged through PR #154 as `44f2467c` on 2026-07-19 |
| `WS-ART-001-02B1` | S3-Compatible MinIO And AWS | L1 | Merged through PR #151 as `1b5422fc` on 2026-07-19 |
| `WS-AUTH-001-09D-A` | Profile Lifecycle And Evidence Repair | L1 | Merged through PR #148 as `99ae4c9` on 2026-07-18 |
| `WS-AUTH-001-09C` | Actor And Identity-Link Administration Reads | L1 | Merged through PR #146 as `0ffdabf` on 2026-07-18 |
| `WS-ENG-001-01` | Codex-native zero-trust loop bootstrap | L1 | Merged through PR #23 on 2026-06-20 |
| `EXAMPLE-TERMINAL-BENCHMARK` | Terminal Benchmark example drill | L3 | Merged through PR #25 on 2026-06-21 |
| `WS-POL-001-PLAN` | Submission Artifact Policy Foundation planning | L1 | Merged through PR #26 on 2026-06-27 |
| `WS-POL-001-01` | Submission Artifact Policy Foundation | L1 | Merged through PR #28 |
| `WS-POL-001-02` | Async Guide Analysis And Policy Derivation | L1 | Merged through PR #61 |
| `WS-POL-001-03` | Task Locked Context And Submission Creation | L1 | Merged through PR #63 on 2026-07-03 |
| `WS-POL-001-04` | Post-Submit Checker Policy Provenance | L1 | Merged through PR #65 |
| `WS-POL-001-05` | Revision Resubmission And Real API Drill | L1 | Merged through PR #66 |
| `WS-POL-001-06` | Terminal Benchmark Real Fixture Drill | L1 | Merged through PR #67 |
| `WS-POL-001-07` | Task Contract Artifact Field Cleanup | L1 | Merged through PR #68 |
| `WS-POL-001-08` | Celery Project Setup Pipeline | L1 | Merged through PR #69 |
| `WS-POL-001-09` | OpenAI Agents SDK Runtime Only | L1 | Merged through PR #71 |
| `WS-POL-001-10` | Pre-Submit Live Drill Hardening | L1 | Merged through PR #72 |
| `WS-POL-001-11` | Actor Identity And Profile Registry | L1 | Merged through PR #74 on 2026-07-07 |
| `WS-POL-001-12` | Project Setup And Policy Visibility APIs | L1 | Merged through PR #76 as `46e74de` |
| `WS-POL-001-13` | Task Context And Submission Requirement APIs | L1 | Merged through PR #77 as `b567bac` on 2026-07-08 |
| `WS-POL-001-14` | Submission Finalize And No-DB Terminal Benchmark Proof | L1 | Merged through PR #79 as `53a57c3` on 2026-07-08 |
| `WS-POL-001-15` | Agent Derivation Policy Conflict Hardening | L1 | Merged through PR #81 as `b1a9851` on 2026-07-08 |
| `WS-POL-001-16` | Terminal Benchmark Live API Drill | L1 | Merged through PR #84 as `a3d2a3f` on 2026-07-09 |
| `WS-POL-002-PLAN` | Post-Submit Checker Foundation Planning | L1 | Merged through PR #85 as `3fc1a68` on 2026-07-09 |
| `WS-POL-002-01` | Post-Submit Compiler Contract | L1 | Merged through PR #87 as `ed52c21` on 2026-07-09 |
| `WS-POL-002-02` | Post-Submit Derivation Agent And Resumable Setup Integration | L1 | Merged through PR #88 as `32af6a7` on 2026-07-11 |
| `WS-POL-002-03` | Server-Owned Policy Approval And Visibility APIs | L1 | Merged through PR #90 as `a7aa474` on 2026-07-11 |
| `WS-AUTH-001-PLAN` | Authorization Service Planning | L0 | Merged through PR #91 as `ad6d644` on 2026-07-11 |
| `WS-AUTH-001-01` | Adopt Authorization Baseline And Repository Contracts | L1 | Merged through PR #93 as `772af1d` on 2026-07-11 |
| `WS-QUAL-001-01B1B-R10` | TypeVar Child Order | L1 | Merged through PR #108 as `5c47aba` on 2026-07-13 |
| `WS-ART-001-PLAN` | Immutable Artifact Storage And Flow Node Integration Planning | L1 | Merged through PR #97 as `8644a43` on 2026-07-12 |
| `WS-QUAL-001-PLAN` | Backend Coverage Floor Planning | L1 | Merged through PR #99 as `9046d52` on 2026-07-12 |
| `WS-ART-001-01` | Artifact Domain And Local Adapter | L1 | Merged through PR #101 as `050eb15` on 2026-07-12 |
| `WS-QUAL-001-01A` | Isolated Database Runner | L1 | Merged through PR #103 as `2901a3e` on 2026-07-12 |
| `WS-QUAL-001-01B1A-R2` | Canonical Coverage Grammar | L1 | Merged through PR #105 as `8a4182e` on 2026-07-12; post-merge memory merged through PR #106 as `6dccb8e` |
| `WS-AUTH-001-02` | Verified Issuer Token And JWKS Boundary | L1 | Merged through PR #107 as `060b780` on 2026-07-13 |
| `WS-AUTH-001-03` | Legacy Actor Classification Preflight | L1 | Merged through PR #109 as `f06532e` on 2026-07-13 |
| `WS-AUTH-001-04A` | Request And Error Context | L1 | Merged through PR #111 as `90c9a28` on 2026-07-13 |
| `WS-AUTH-001-04B` | PostgreSQL Rate Controls | L1 | Merged through PR #113 as `05a63c8` on 2026-07-14 |
| `WS-AUTH-001-05A` | Shared Audit Ownership And Append-Only Authority Evidence | L1 | Merged through PR #115 as `8e1cde6` on 2026-07-14 |
| `WS-AUTH-001-CAT` | Action And Resource Catalogue Reconciliation | L1 | Merged through PR #117 as `4c5d4fc` on 2026-07-14 |
| `WS-AUTH-001-CAT-MEMORY` | Catalogue Post-Merge Memory | L1 | Merged through PR #118 as `eba7e2b` on 2026-07-14 |
| `WS-AUTH-001-05B` | Authority Idempotency And Invalidation Foundation | L1 | Merged through PR #119 as `ad71c7e` on 2026-07-14 |
| `WS-AUTH-001-06` | Canonical Actor Profile And Identity Link | L1 | Merged through PR #124 as `f599551` on 2026-07-15 |
| `WS-AUTH-001-07A` | Closed Permission And Action Catalogue | L1 | Merged through PR #126 as `e9d72a1` on 2026-07-15 |
| `WS-AUTH-001-07B` | Deny-By-Default Kernel And Self-Action Cutover | L1 | Merged through PR #130 as `90eca12` on 2026-07-15 |
| `WS-AUTH-001-08` | Bootstrap Access Administrator Grant | L1 | Merged through PR #131 as `aa0fdcd` on 2026-07-16 |
| `WS-AUTH-001-09A` | Fixed Service Identity Foundation | L1 | Merged through PR #132 as `299363a` on 2026-07-17 |
| `WS-AUTH-001-09B` | Controlled Service Actor Provisioning | L1 | Merged through PR #143 as `053242b` on 2026-07-17 |
| `WS-XINT-001-PLAN` | Lifecycle Boundary Reconciliation | L1 | Merged through PR #139 as `5d353b6` on 2026-07-17 |
| `WS-ART-001-OBJECT-STORAGE-AMENDMENT` | AWS-First Object Storage Planning Amendment | L1 | Merged through PR #120 as `4408256` on 2026-07-14 |
| `WS-ART-001-02A1` | External Service Adapter Foundation | L1 | Merged through PR #127 as `f64a8e5` on 2026-07-15 |
| `WS-ART-001-02A2` | Committed Source And Local Preparation | L1 | Merged through PR #129 as `9a04434` on 2026-07-16 |
| `WS-ART-001-02A3` | ArtifactStore v2 Local Clean Cut | L1 | Merged through PR #141 as `a10d901` on 2026-07-18 |
| `WS-AUTH-001-XINT` | Lifecycle Boundary Plan Reconciliation | L1 | Merged through PR #140 as `d541521` on 2026-07-17 |
| `WS-ENG-001-02` | Automated Post-Merge Memory | L1 | Merged through PR #122 as `fc89fb6`; schema-v1 output superseded by WS-ENG-001-03 |

## Proposed Next

AUTH-05A merged through PR #115 as `8e1cde6`, and CAT plus its post-merge memory
merged through PRs #117 and #118. AUTH-05B merged through PR #119 as `ad71c7e`.
AUTH-06 merged through PR #124 as `f599551`. AUTH-07A, AUTH-07B, and AUTH-08
merged through PRs #126, #130, and #131. WS-XINT planning merged through PR #139,
and its AUTH owner reconciliation merged through PR #140 as `d541521`.
AUTH-09A merged through PR #132 as `299363a`, and signed schema-v2 memory
stopped. AUTH-09B merged through PR #143 as `053242b`; the user then explicitly
started AUTH-09C. PR #146 merged it as `0ffdabf`; signed memory at `eeb3dc2`
stopped. The user explicitly started AUTH-09D, and required review split it
before runtime edits. PR #148 merged 09D-A as `99ae4c9`; signed memory
`cf8a3e8` stopped and named 09D-B. PR #152 merged 09D-B as `93dd392`; signed
memory `912a6254` passed and stopped. The user explicitly started the
contributor foundation from that trusted head. Its first L1 review rejected the
underspecified contract before runtime edits; exact contract repair and
rereview are current. AUTH-09E and POL-002-04 remain inactive pending their own
gates and explicit starts.

Coverage R10 merged through PR #108. Do not start 01B2, chunk 02, or another
coverage implementation chunk from this worktree.

`WS-ART-001-01`, the AWS-first planning amendment, `02A1`, `02A2`, `02A3`, and
`02B1` are merged; PR #151 merged `02B1` as `1b5422fc`. R2 and Flow Node are
deferred. The user explicitly started `02C1` on 2026-07-19. `02C2` remains
inactive until `02C1` merges and receives a separate explicit start.

Coverage work proceeds independently in its own worktree and is not owned by
this AUTH queue update.

## Blocked

| Chunk | Blocker | Next action |
|---|---|---|
| `WS-QUAL-001-01B1` | 496/500 lines after two semantic-integrity repair cycles | Superseded by the proposed 01B1A/01B1B split; do not resume |
| `WS-QUAL-001-01B1A` | 394/400 lines after two parser-normalization repair cycles; final QA/security review found two valid bypass variants | Replan the parser boundary before any further implementation |
| `WS-QUAL-001-01B1A-R1` | Additional valid false-positive finding outside its two-fix contract | Superseded by R2 canonical-grammar proposal; do not resume |
| `WS-QUAL-001-01B1B` | 223/300 after two binding/AST repair cycles; final test-delta review found lexical-shadow false positives and a weakened local-skipTest expectation | Superseded through stopped R1-R9 by reviewed B1B-R10; do not resume |
| `WS-QUAL-001-01B1B-R7` | Final review after two repair cycles found wrapper provenance, qualified/async consumer, relative-import, class-expression, and readability gaps | Superseded by reviewed B1B-R10; do not repair in place |
| `WS-QUAL-001-01B1B-R8` | Final QA found Python 3.11 comprehension symtable incompatibility after two repairs | Superseded by reviewed B1B-R10; do not repair in place |
| `WS-QUAL-001-01B1B-R9` | Final review found shared Python 3.13 TypeVar bound/default child ordinals | Superseded by reviewed B1B-R10; do not repair in place |
| `WS-QUAL-001-01B1B-R1` | Shared resolver measured 282 lines before its required behavior matrix, exceeding the 270 checkpoint and making the 300 cap infeasible | Superseded through stopped R2-R9 by reviewed B1B-R10; no implementation draft retained |
| `WS-QUAL-001-01B1B-R2` | 348/350 candidate failed cycle-zero implementation review on standard lexical/control-flow cases with only two lines reserve | Superseded through stopped R3-R9 by reviewed B1B-R10; do not repair in place |
| `WS-QUAL-001-01B1B-R3` | 468/500 cycle-zero candidate; required control/value-flow repair plus tests did not credibly fit 32 lines | Superseded through stopped R4-R9 by reviewed B1B-R10; no cycle-one code edit made |
| `WS-QUAL-001-01B1B-R4` | 535/550 cycle-zero candidate replayed AST scopes and missed target/unpack/comprehension semantics | Superseded through stopped R5-R9 by reviewed B1B-R10; do not repair in place |
| `WS-QUAL-001-01B1B-R5` | 641/650 cycle-zero candidate; provenance closure/evaluation order/except-star proof could not fit nine lines | Superseded through stopped R6-R9 by reviewed B1B-R10; do not repair in place |
| `WS-QUAL-001-01B1B-R6` | 800/800 cycle-one candidate; iterable abstraction and class-global proof remained incomplete | Superseded through stopped R7-R9 by reviewed B1B-R10; do not repair in place |
