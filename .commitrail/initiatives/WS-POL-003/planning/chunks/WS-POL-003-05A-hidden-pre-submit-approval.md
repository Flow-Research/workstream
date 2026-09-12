# Chunk Contract: WS-POL-003-05A - Hidden Pre-Submit Approval

Status: Complete (hidden boundary; public AUTH-12F4/POL-05B remains). Risk: L1.

## Goal

Build hidden PM approval and trusted effective/pre-submit projection behavior
over the complete immutable unified result.

## Allowed files

Project approval/policy service/repository/schema, CHECKERS catalogue/compiler
integration and affected ART/TASK consumers, bounded unified-review/correction schemas and shared compilation
input contracts, deny-by-default AUTH seam, focused tests, and WS-POL-003 docs.

## Not allowed

Action activation, public live approval, model calls, post projection,
new checker execution activation, second compiler/registry, or in-place proposal edits.
Existing pre-submit consumers must accept the canonical approved policy: preserve
opaque guide versions and recognize its inspected-byte artifact hash manifest.

## Acceptance

- Approval input binds compilation/result/artifact/pre/post component hashes,
  source/setup generation, and both catalogue snapshots.
- The full proposal is reviewable before approval. Every capability-gap
  disposition blocks under the current schema; ordinary non-blocking
  sufficiency warnings may be acknowledged. Do not invent optional capability
  gaps or turn unsupported automation into human review without explicit
  project-approved classification.
- Mandatory platform entries cannot be selected, repeated, weakened, or
  reordered; stale lineage denies.
- Candidate effective/pre writes remain hidden and denied until AUTH-12F4.
- PROJECTS owns separate append-only approval/operation provenance keyed to
  the exact finalized setup receipt, compilation and proposed policy hashes.
  Existing canonical policy rows retain their own lifecycle; do not update a
  finalized `ProjectSetupRun`, its timestamp, outputs or receipt to record an
  approval. Choose the owner-local table/constraints in this hidden boundary,
  not in AUTH-12F4 or live 05B.
- The effective policy is mandatory platform defaults plus the approved
  project artifact policy, compiled by the existing CHECKERS-owned compiler into
  the exact pre-submit plan. Project requirements can strengthen/configure
  supported rules but cannot remove or duplicate platform work. Unknown
  required rules remain explicit gaps; do not invent defaults for them.
- Preserve review/revision policy configuration as separately validated,
  versioned PROJECTS guide inputs for later activation, not REV runtime work.

## Review before approval and setup-wide correction

Existing setup-run and post-policy reads are not a complete review package.
PROJECTS owns an exact-compilation bounded projection containing sufficiency
findings, artifact proposal, requirements/dispositions, pre/post bindings,
capability suggestions, safe notes and component/catalogue/generation lineage.
The package contains guide-derived prose and requires current exact-project
Project Manager guide-content authority (`project.guide.manage`), not Operator
or Audit diagnostic authority. It excludes raw document payloads, model
reasoning, credentials, runtime handles, replayable references and hidden
provider payloads; prose validation is not a promise of semantic DLP. Approval must name exactly the displayed target
and hashes; a latest-only diagnostic response is insufficient.

The hidden setup-wide correction request acts on a known finalized setup
result, including an already approved predecessor. Bind exact known finalized compilation/result/components, normalized
bounded reason and predecessor. Record a separate immutable correction
operation and allocate one successor generation through the existing unified
request/attempt machinery. Version its bounded feedback input contract where
needed; no legacy post-only inference or finalized-row mutation. Idempotent
replay creates no additional successor. This corrects a known terminal result;
it is not permission to restart an uncertain provider operation under a new key.

AUTH-12F4 supplies exact read/correction authority; POL-05B exposes these same
commands before enabling approval. POL-08 cannot own these prerequisites later.
Prove real authorized GET -> approval of those exact hashes, no raw disclosure,
stale/mixed result denial, artifact/pre correction before post approval, one
successor on replay, and byte-for-byte preservation of prior finalization.

## Verification and review

Compiler parity, full-result-before-approval, gap, stale-hash, and denial tests;
real PostgreSQL approval provenance, immutable-finalization and rollback proof.
Required reviews: architecture, security, QA, product/operations.
Human focus: complete proposal and no inference at approval.
