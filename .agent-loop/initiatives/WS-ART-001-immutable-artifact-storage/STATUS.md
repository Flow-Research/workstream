# Status: WS-ART-001 Immutable Artifact Storage

## Audited Durable State At 2026-08-02

ART-03A and every split ART-03B chunk through 03B4 are merged. The complete
verified guide binding, materialization, classification, extraction, and hidden
same-generation sufficiency continuation exist on `main`.

AUTH-04A activated `artifact.guide_source.ingest`. AUTH-04B production
implementation merged in PR #245 at `6babf81b`. The fixed guide binding and
guide-reader services are live, and
`artifact.guide_source.binding.create` plus `artifact.guide_source.read` are
active under `XINT_002_04B`. ART-03C's dependency is satisfied.

`WS-ART-001-PLAN3` is the planning-only end-to-end audit of remaining v0.1
work. It splits oversized chunks, repairs activation order, and adds explicit
reviewer/contribution custody handoffs. It starts no implementation.

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

## Completed Guide Pipeline And Current Submission Work

ART-03A and AUTH `WS-XINT-002-04A` are merged. The guide-content boundary was
implemented explicitly as verified binding,
full-read materialization, format classification, isolated extraction,
canonical extraction provenance, incremental complex-format support, and
same-generation sufficiency continuation are separate PR-sized contracts.
`WS-ART-001-03B4` is merged: its reviewed contract fixes the artifact-owned
material port, all-items-required semantics, deterministic 12 MiB assembly,
normalized report-to-extraction provenance, and the hidden pre-submit
identifier/generation continuation. AUTH binding/read production activation
merged through PR #245, and ART-03C's verified-pipeline cutover subsequently
merged.

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

03B1 merged through PR #222, 03B2 through PR #223, and 03B3A through PR #225.
03B3B2 is merged through PR #231. It installs only the approved `pypdf` wheel
and adds bounded passive-PDF text extraction inside the existing isolated
child.

03B3B3A merged through PR #233. It installs only the approved `defusedxml`
wheel and adds the shared bounded OPC/OOXML container security capability.
03B3B3B merged through PR #234. It adds bounded DOCX extraction and durable
omission facts on the shared OOXML boundary. 03B3B3C merged through PR #235 and
adds bounded PPTX slide/notes extraction. 03B3B3D merged through PR #238 and
adds bounded XLSX cell extraction. 03B3B4 merged through PR #239 and adds only
bounded PNG/JPEG/WebP structural metadata. 03B4 merged through PR #240 and adds
the hidden same-generation sufficiency continuation. ART-03C and ART-04A1 are
merged. ART-04A1 merged through PR #264, and ART-04A2 merged through PR #266.

AUTH `WS-XINT-002-04B` activated only fixed-service binding and guide read.
ART-03C removed the legacy identity/excerpt path and made the verified pipeline
authoritative. ART-04A3 merged through PR #268
and provides canonical server-derived semantic manifests, executable
normalization, and fail-closed unchanged-work comparison.

`WS-ART-001-PLAN4` merged through PR #271. Discovery for its proposed 04A4
implementation proved the early clean cut unsafe because live legacy Submission
creation still calls the shared precheck service and the verified-admission
replacement is not yet available. PLAN5 merged through PR #273: it
supersedes 04A4, makes 04B1 the next implementation chunk, and assigns complete
legacy route/public-service/internal-guard/caller-package removal to the 05B
admission-backed Submission cutover.

`WS-ART-001-04B1` merged through PR #276 and supplies the immutable typed
catalogue plus lineage-bound effective plan. `WS-ART-001-04B2` merged through
PR #282. It owns only fixed-service authorization before byte access,
quota-reserved callback-scoped sealed ZIP projection, platform/default phase
execution, bounded non-durable results, and cleanup. It performs no
project-policy execution, durable evidence/admission/Submission write, route
exposure, provider I/O, or AUTH activation. `WS-ART-001-04B3` merged through
PR #291 as `8f516e6d`. It executes the project-policy continuation through that
same plan and sealed tree and persists one immutable platform-plus-project
evidence set. AUTH `WS-XINT-002-06A` merged through PR #293 as `1ddb941e` and
activated only the mandatory fixed pre-submit materializer. ART-04C1 then
merged through PR #296 and persists the evidence-linked durable put intent.
The dependency-ordered successor is 04C2; open pull requests determine whether
it is currently under review.

## Gate

Planning evidence and all required internal reviewer tracks must pass before a
PR. Every implementation chunk retains its own bounded contract, exact AUTH
activation sequence, internal review, CI, CodeRabbit, and human checkpoint.
