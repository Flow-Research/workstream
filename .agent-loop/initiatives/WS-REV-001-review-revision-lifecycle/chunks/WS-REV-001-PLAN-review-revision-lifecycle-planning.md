# Chunk Contract: WS-REV-001-PLAN

## Goal

Reconcile the revised WS-REV source with the current repository and produce a
reviewed end-to-end initiative plan without changing runtime behavior.

## Risk class

L1 planning with a narrowly scoped CI documentation-gate correction.

## Allowed files

```text
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/initiatives/WS-XINT-001-lifecycle-boundary-reconciliation/REV_CON_HANDOFF.md only to apply the human-approved FinalAcceptance and two-operation transaction amendment
.agent-loop/merge-intents/WS-REV-001-PLAN.json
docs/reference_specs/WS-REV-001-review-lifecycle-specification.md
docs/reference_specs/WS-REV-001-review-lifecycle-specification.pdf
docs/reference_specs/README.md only for exact canonical WS-REV provenance/hash rows and directly associated provenance/checksum prose
docs/reference_specs/SHA256SUMS only for exact canonical WS-REV hash rows
.gitattributes only for the canonical byte-immutable WS-REV Markdown whitespace classification
scripts/check_stale_authorization_docs.py only to recognize exact technical execution-package paths and live-drill CLI flags
scripts/test_agent_gates.py only for the matching false-positive and fail-closed regressions
```

## Not allowed

```text
backend/**
docs/reference_specs/** except the four exact canonical-reference repairs above
docs active product/architecture/operations files
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
runtime implementation or dependency changes
```

## Acceptance criteria

- Revised Markdown and PDF are read end to end; heading/token parity and their
  non-identical status wording are recorded without claiming byte-derived
  semantic equivalence.
- The supplied revised Markdown/PDF contents live at the canonical WS-REV
  filenames, their hashes match README/SHA256SUMS, and no duplicate `(2)` path
  remains.
- Git classifies the canonical revised Markdown's supplied hard-break trailing
  spaces path-specifically; no global whitespace rule is weakened.
- Current task, submission, checker, auth, artifact, contribution, audit,
  job execution, API, migration, test, and documentation boundaries are cited.
- Merged WS-XINT-001 PR #139, ADR 0015, and all four owner handoffs are treated
  as current authority. The plan distinguishes AUTH action activation from REV
  product release and derives future catalogue counts from exact trusted main.
- Merged AUTH reconciliation PR #140 is the exact planning authority for REV
  activation custody, prepared mutations, registration, service identity, and
  per-feature activation gates. It changed no runtime catalogue or availability.
- Merged AUTH-09A PR #132 is the current runtime authority for migration `0023`,
  the seven-identity/eleven-membership ART service matrix, and the 65-action
  catalogue split into 9 active and 56 planned actions. It provisions no actor,
  admits no service token, activates no action, and contains none of REV's six
  proposed identities; all 24 REV dependencies remain unavailable.
- The shared REV/CON handoff records the approved accept-only FinalAcceptance
  source and ordered reviewer/submitter CON operations; it no longer presents
  the superseded one-call contribution or CON-owned audit/outbox sequence.
- Independent reviewer grants, AUTH-09A-compatible REV identity extensions with
  AUTH-09B provisioning and AUTH-09E admission, AUTH-first prepared
  mutations, ART v2 packet/evidence ports, ReviewPacketManifest,
  ReviewEvidenceArtifact, flush-only CON integration, stabilized artifact_hash
  lineage, and optional contribution evidence are closed across all artifacts.
- Every valid decision appends an immutable Review; every submitted finding and
  later resolution is immutable; later rounds append rather than overwrite.
- The plan defines one internal immutable FinalAcceptance only as a consequence
  of `Review(accept)`, maps conceptual submission-version identity to existing
  `Submission.id`, binds the exact ReviewPolicy context and canonical actors,
  enforces unique task/Review/Submission lineage, and adds no separate create
  action or public/manual API.
- Reviewer `completed_review` lineage remains direct from Review and ReviewLease.
  Submitter `accepted_submission` lineage requires FinalAcceptance and never
  infers acceptance directly from `Review.decision`.
- REV owns decision orchestration and shared audit/outbox staging inside the
  caller transaction; the request route or service command owns the caller
  `AsyncSession` and only commit. CON is a
  mandatory participant with an ordered reviewer operation before the decision
  branch and a submitter operation only after FinalAcceptance exists.
  Both operations are flush-only, return typed audit and outbox inputs, never
  commit, and perform no ART or provider call.
- Observations, decisions, risks, unknowns, and dependencies are separated.
- Every proposed chunk has scope, exclusions, testable criteria, risk,
  verification, reviewers, and human focus.
- Specification sections 25.1-25.9 have an executable conformance matrix.
- First implementation chunk remains proposed and inactive.
- Exactly one merge intent names WS-REV-001-01 as the successor and requires a
  separate explicit start; it does not activate that chunk.
- The AUTH stale-documentation gate recognizes only exact technical execution-
  package paths and the existing live-drill execution flags; human contributor-
  role wording remains rejected by regression tests.

## Verification

```text
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/test_agent_gates.py
sha256sum -c docs/reference_specs/SHA256SUMS
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test-delta, and CI integrity.

## Human review focus

Archival provenance, immutable Review/finding/resolution history,
FinalAcceptance lineage and uniqueness, transaction ownership, provider
correction, revision-limit behavior, controlled rebase, server-selected review
offers, cross-initiative gates, and coherent production activation only after
recovery/operations/live proof.

## Stop condition

Present the plan and wait for explicit human approval. Do not start 01.
