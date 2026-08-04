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
| `WS-ART-001-PLAN3` | Reconcile the complete remaining v0.1 custody chain and AUTH/REV/CON handoffs. | L1 | Planning only; proposed |
| `WS-ART-001-03C` | Clean-cut legacy guide identity/excerpts and make the verified same-generation pipeline live. | L1 | Merged PR #249 |
| `WS-ART-001-04A1` | Remove legacy multi-step contributor intake reachability and schema without adding the replacement route. | L1 | Merged PR #264 |
| `WS-ART-001-04A2` | Add bounded one-outer-ZIP intake and archive-safety inspection in private scratch. | L1 | Implemented; internal review passed; external PR gates pending |
| `WS-ART-001-04A3` | Add canonical semantic manifest, executable normalization, and unchanged-work gate. | L1 | Proposed after 04A2 |
| `WS-ART-001-04B` | Run non-bypassable platform and locked-guide prechecks against that exact scratch tree and persist bounded evidence. | L1 | Proposed after 04A3 |
| `WS-ART-001-04C1` | Reauthorize and atomically persist capacity plus durable put intent, then write the checked ZIP once. | L1 | Proposed after XINT-06A |
| `WS-ART-001-04C2` | Reuse verification/recovery to publish one capacity-charged ready admission and compose the hidden continuous endpoint. | L1 | Proposed after 04C1 |
| `WS-ART-001-05A` | Atomically consume ready admission into one immutable Submission and binding under fresh human/service authority. | L1 | Proposed after XINT-05A |
| `WS-ART-001-05B` | Remove legacy package URI/hash/manifest authority and cut live API/automatic post-submit dispatch to the verified binding. | L1 | Proposed after XINT-05B |
| `WS-ART-001-06A` | Persist post-submit checker input snapshot and integrity-checking materialization. | L1 | Proposed after 05B |
| `WS-ART-001-06B` | Store/bind checker outputs and preserve checker-owned routing. | L1 | Proposed after 06A |
| `WS-ART-001-07A` | Add lease-scoped exact-binding reviewer packet materialization without review lifecycle ownership. | L1 | Proposed after 06B plus hidden REV manifest |
| `WS-ART-001-07B` | Bind accepted Submission/ART identity into the CON handoff without provider I/O. | L1 | Proposed after REV acceptance and CON hidden contract |
| `WS-ART-001-08A` | Prove Local/MinIO product lifecycle through real APIs and durable background services. | L1 | Proposed after 07B |
| `WS-ART-001-08B` | Prove AWS production readiness and bounded activation independently of product behavior. | L1 | Proposed after 08A or concurrently once product contracts are stable |
| `WS-ART-001-08C` | Run final ART/AUTH/REV/CON conformance for the complete v0.1 custody chain. | L1 | Proposed after ART 08A/08B and XINT-08 |

## Corrected Cross-Initiative Order

```text
AUTH-04B implementation [merged PR #245]
-> ART-03C
-> ART-04A1 -> 04A2 -> 04A3 -> 04B
-> XINT-06A pre-submit materializer activation
-> ART-04C1 -> 04C2
-> XINT-05A contributor preparation activation
-> ART-05A
-> XINT-05B Submission/binding activation
-> ART-05B -> 06A -> 06B
-> XINT-06B post-submit/output activation
-> ART/REV-07A hidden packet contract
-> XINT-07A packet activation only
-> REV acceptance -> ART/CON-07B identity handoff
-> ART-08A + ART-08B
-> XINT-08 + ART-08C
```

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
