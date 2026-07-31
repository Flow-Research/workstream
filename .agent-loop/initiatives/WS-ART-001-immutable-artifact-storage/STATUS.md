# Status: WS-ART-001 Immutable Artifact Storage

## Completed Foundation

Planning and the artifact foundation merged through PR #97 and PR #101. The
AWS-first object-storage amendment and typed adapter clean cut merged through
PRs #120, #127, #129, #141, and #151. Durable admission, put attempts,
verification/publication, recovery idempotency, and hidden Operator operations
merged through PRs #154, #159, #174, and #177 (`WS-ART-001-02D`).

The current v0.1 provider direction remains AWS S3 in production, MinIO for
local/CI protocol proof, and LocalStorage for development/focused tests. Flow
Node and R2 remain deferred. Completed objects have no physical deletion path.
AUTH's owner reconciliation merged through PR #140 as
`d541521`; PLAN2 preserves AUTH ownership and proposes no availability edit.

## Cancelled Work

`WS-ART-001-03` received a signed implementation start on current history, but
mandatory preimplementation review rejected the combined contract before any
runtime edit. The user authorized cancellation, and signed automation run
`30100940860` recorded `stopped_after_cancel` on 2026-07-24. The rejected
contract combined guide byte ingest, binding, materialization, setup recovery,
migration, and inactive AUTH dependencies without a safe executable boundary.

## Current Planning Reconciliation

`WS-ART-001-PLAN2` is planning-only. It incorporates the human-approved
submission invariant:

```text
one outer ZIP
-> bounded private scratch inspection and canonical manifest
-> exact/semantic unchanged rejection
-> mandatory platform and locked Project Guide prechecks
-> one existing ArtifactStore admission and complete read-back verification
-> one immutable Submission binding
-> the same bytes checked, reviewed, accepted, recorded, and delivered
```

There is no candidate store, temporary provider retention, promotion copy,
physical deletion, second recovery aggregate, speculative capacity increase, or
competing `SubmissionVersion` table. Reviewers attach a decision plus
note/findings to the
exact `Submission`; contributors answer `needs_revision` with another complete
ZIP and immutable Submission.

PLAN2 also treats client-abandoned verified admissions as valid, bounded,
capacity-charged `ready` facts with terminal `consumed|stale` outcomes; it
normalizes regular-file executable intent into the semantic manifest; and it
requires fresh AUTH prepared capabilities at durable put intent and atomic
Submission/binding consumption.

## Current Planning Correction

ART-03A and AUTH `WS-XINT-002-04A` are merged. Before ART-03B implementation,
the guide-content boundary is being corrected explicitly: verified binding,
full-read materialization, format classification, isolated extraction,
canonical extraction provenance, incremental complex-format support, and
same-generation sufficiency continuation are separate PR-sized contracts.
`WS-ART-001-03B1` is the first proposed
implementation successor; this planning change contains no implementation.

After 03B3A merged, the original complex-format chunk was found too broad for
one dependency and parser-security review. It is replaced by 03B3B1 dependency
approval, 03B3B2 PDF, 03B3B3A shared OOXML security, separate 03B3B3B DOCX,
03B3B3C PPTX, and 03B3B3D XLSX adapters, and 03B3B4 image metadata. No dependency is
installed until the human owner approves 03B3B1's exact pinned allowlist.

03B3B1 is merged through PR #230 as the dependency-decision and CI-only chunk.
It approved exact hashed wheels for `pypdf`, `defusedxml`, and `Pillow`, with no
package, lock, runtime import, or parser behavior change. Its approval gate
requires independent protected GitHub review of the exact final PR head before
merge; repository-authored evidence alone is not authority.

03B3B2 is merged through PR #231. It installs only the approved `pypdf` wheel
and adds bounded passive-PDF text extraction inside the existing isolated
child.

03B3B3A merged through PR #233. It installs only the approved `defusedxml`
wheel and adds the shared bounded OPC/OOXML container security capability.
03B3B3B merged through PR #234. It adds bounded DOCX extraction and durable
omission facts on the shared OOXML boundary. 03B3B3C merged through PR #235 and
adds bounded PPTX slide/notes extraction. 03B3B3D is the active successor and
adds only bounded XLSX cell extraction. Image, AUTH, and sufficiency work remain
inactive.

AUTH `WS-XINT-002-04B` follows the complete hidden split-03B series and
activates only fixed-service binding and guide read. ART-03C then removes the
legacy identity/excerpt path and makes the verified pipeline authoritative.

## Gate

Planning evidence and all required internal reviewer tracks must pass before a
PR. Every implementation chunk retains its own bounded contract, exact AUTH
activation sequence, internal review, CI, CodeRabbit, and human checkpoint.
