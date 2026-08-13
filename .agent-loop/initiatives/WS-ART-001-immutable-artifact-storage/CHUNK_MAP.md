# Chunk Map: WS-ART-001 Immutable Artifact Storage

Each chunk is one PR. No later chunk starts automatically.

## Durable Merged Work

| Range | Outcome | Status |
|---|---|---|
| `PLAN`, `01`, object-storage amendment | Original plan, artifact domain, AWS-first correction | Merged |
| `02A1`-`02A3` | Typed adapter foundation, bounded scratch, ArtifactStore v2 clean cut | Merged |
| `02B1` | S3-compatible adapter, MinIO, AWS profile | Merged |
| `02C1`-`02D` | Admission, put/verification fencing, recovery, Operator surfaces | Merged |
| `PLAN2` | One-ZIP and guide/submission reconciliation | Merged planning |
| `03A` | Guide-source opaque-byte ingest | Merged PR #215 |
| `03B1`-`03B4` | Binding, generation, materialization, extraction, canonical sufficiency | Merged through PR #240 |

The original combined `03` was cancelled before implementation. The original
future `04A`, `04C`, `05`, and `07` contracts are superseded by PLAN3 because
they cross multiple L1 boundaries.

## Remaining v0.1 Chunks

| Chunk | Goal | Risk | Entry gate/status |
|---|---|---:|---|
| `WS-ART-001-PLAN3` | Reconcile the complete remaining v0.1 custody chain and AUTH/REV/CON handoffs. | L1 | Merged planning |
| `WS-ART-001-PLAN4` | Define the central default pre-submission checker catalogue, disable semantics, and split execution contract. | L1 | Merged PR #271 |
| `WS-ART-001-PLAN5` | Correct legacy-precheck removal sequencing so the old public and internal paths are deleted only with the admission-backed Submission cutover. | L1 | Merged PR #273 |
| `WS-ART-001-03C` | Clean-cut legacy guide identity/excerpts and make the verified same-generation pipeline live. | L1 | Merged PR #249 |
| `WS-ART-001-04A1` | Remove legacy multi-step contributor intake reachability and schema without adding the replacement route. | L1 | Merged PR #264 |
| `WS-ART-001-04A2` | Add bounded one-outer-ZIP intake and archive-safety inspection in private scratch. | L1 | Merged PR #266 |
| `WS-ART-001-04A3` | Add canonical semantic manifest, executable normalization, and unchanged-work gate. | L1 | Merged PR #268 |
| `WS-ART-001-04A4` | Former early removal of the legacy independently invocable caller-owned submission-precheck route and contract. | L1 | Superseded by PLAN5; complete removal belongs to deferred WS-ARCH-001-02I |
| `WS-ART-001-04B1` | Add the single versioned checker catalogue and compile one effective execution plan from platform defaults plus locked project policy. | L1 | Merged PR #276 |
| `WS-ART-001-04B2` | Materialize the sealed manifest tree once and execute the mandatory platform/default catalogue phases. | L1 | Merged PR #282 |
| `WS-ART-001-04B3` | Execute locked project-policy rules through the same plan and persist one bounded immutable evidence set. | L1 | Merged PR #291 as `8f516e6d` |
| `WS-ART-001-04C1` | Reauthorize and atomically persist the evidence-linked submission intent, capacity, and generic put attempt, then write the checked ZIP once. | L1 | Merged PR #296 |
| `WS-ART-001-04C2` | Reuse verification/recovery to publish one capacity-charged ready admission and compose the hidden continuous endpoint. | L1 | Merged PR #300 as `b2e2c615` |
| `WS-ART-001-05A` | Historical ART admission/binding plus Submission coordination proposal. | L1 | Superseded/non-executable; replaced by WS-ARCH-001-02E/02F |
| `WS-ART-001-05B` | Historical live Submission API/dispatch cutover proposal. | L1 | Superseded/non-executable; replaced by WS-ARCH-001-02I after 02A-02H |
| `WS-ART-001-06A` | Historical post-submit checker input/materialization proposal. | L1 | Planned retirement as superseded/non-executable; WS-ARCH-001-04A-04D owns the split replacement |
| `WS-ART-001-06B` | Historical checker-output binding/routing proposal. | L1 | Planned retirement as superseded/non-executable; WS-ARCH-001-04C-04E owns the split replacement |
| `WS-ART-001-07A` | Add lease-scoped exact-binding reviewer packet materialization without review lifecycle ownership. | L1 | Proposed after canonical WS-ARCH-001-04E plus an exact hidden REV manifest |
| `WS-ART-001-07B` | Bind accepted Submission/ART identity into the CON handoff without provider I/O. | L1 | Proposed after REV acceptance and CON hidden contract |
| `WS-ART-001-08A` | Prove Local/MinIO product lifecycle through real APIs and durable background services. | L1 | Proposed after 07B |
| `WS-ART-001-08B` | Prove AWS production readiness and bounded activation independently of product behavior. | L1 | Proposed after 08A or concurrently once product contracts are stable |
| `WS-ART-001-08C` | Run final ART/AUTH/REV/CON conformance for the complete v0.1 custody chain. | L1 | Proposed after ART 08A/08B and XINT-08 |

## Corrected Cross-Initiative Order

```text
AUTH-04B implementation [merged PR #245]
-> ART-03C
-> ART-04A1 -> 04A2 -> 04A3 -> PLAN4 -> PLAN5 -> 04B1 -> 04B2 -> 04B3
-> XINT-06A pre-submit materializer activation
-> ART-04C1 -> 04C2
-> WS-ARCH-001-01 boundary foundation
-> WS-ARCH-001-02A-02F hidden public-capability/transaction foundations
-> WS-ARCH-001-02G/02H exact AUTH activation
-> POL-06B -> POL-07
-> WS-ARCH-001-03/04 current task/readiness and canonical post-submit
   materialization/checker/output activation
-> WS-ARCH-001-05 REV-admission prerequisites
-> WS-ARCH-001-02I live admission-only clean cut
-> ART/REV-07A hidden packet contract
-> XINT-07A packet activation only
-> REV acceptance -> ART/CON-07B identity handoff
-> ART-08A + ART-08B
-> XINT-08 + ART-08C
```

The former ART-06A/06B -> XINT-06B row is historical and non-executable.
WS-ARCH-001 PLAN2 is the only current owner of that split capability path.

XINT-05C checker remediation and XINT-05D human-review revision reuse the same
one-ZIP preparation/Submission primitives only after their CHECKER/REV-owned
obligation contracts exist. They do not create alternate artifact intake.

Review-evidence upload/binding is not part of the approved v0.1 reviewer
workflow and remains planned/unavailable. A reviewer records only
`accept|needs_revision|reject` plus note/findings. Client delivery and physical
deletion remain future initiatives.

## Ownership Boundaries

- ART owns bytes, digest/size, semantic manifests, verified content, bindings,
  incidents, and integrity-checking materialization.
- AUTH owns action/permission catalogues, fixed identities/matrices, prepared
  authority, evidence, and availability.
- TASK owns assignment, locked context, Submission lifecycle, predecessor, and
  automatic checker dispatch.
- CHECKER owns checker policy, execution, findings, and routing.
- REV owns review packet manifest, queue/lease/assignment, decision, and
  note/findings.
- CON owns ContributionRecord and references the accepted Submission/ART
  identity without reading provider bytes.
