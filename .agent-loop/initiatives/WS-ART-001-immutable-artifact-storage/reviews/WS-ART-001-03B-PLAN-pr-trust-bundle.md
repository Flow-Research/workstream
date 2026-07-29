# PR Trust Bundle: WS-ART-001-03B Planning Correction

## Chunk

`WS-ART-001-03B-PLAN` — planning-only correction before implementation.

## Goal

Define the safe path from verified Project Manager guide-source bytes to exact
same-generation sufficiency input without confusing it with contributor ZIPs.

## Human-Approved Intent

- contributors always submit one outer ZIP;
- Project Managers upload guide items in supported document/data/image formats;
- v0.1 excludes audio and video;
- upload stores opaque bytes and performs no synchronous parsing;
- AUTH later activates only fixed-service guide binding and read.

## What Changed And Why

The old 03B contract combined too many boundaries. It is now five executable
PRs: `03B1 -> 03B2 -> 03B3A -> 03B3B -> 03B4 -> AUTH-04B -> 03C`.

## Design Chosen

Original bytes remain authoritative in `ArtifactStore`. Existing materialization
and scratch capabilities rehash every full read. Content-derived extraction is
separate from binding/run/generation usage. Canonical extraction is bounded
PostgreSQL processing evidence, not an unapproved provider write. Agent input
is typed, bounded, provenance-linked, and explicitly untrusted.

## Alternatives Rejected

Parsing in upload, forcing guides into contributor ZIPs, direct provider access,
a second scratch manager, one large parser PR, image OCR by implication, raw
binary/excerpt agent input, and provider writes under guide-read authority.

## Scope Control And Product Behavior

Planning/specification only. Guide items support PDF, DOCX, PPTX, CSV, XLSX,
Markdown, text, JSON, and PNG/JPEG/WebP metadata. Audio/video and ordinary ZIP
guide semantics are unsupported. Artifact/extraction failures create redacted
`setup_blocked` outcomes, not guide-insufficiency decisions.

## Acceptance Proof, Test Delta, And CI Integrity

- diff, Markdown links, stale artifact contracts, and stale wording: PASS;
- no executable CI/test/package delta;
- every future contract names focused tests, Ruff, 90% changed-subsystem
  coverage, the 78% repository gate, Agent Gates, and hosted Backend checks;
- 03B3B requires a human-approved, CI-enforced parser dependency allowlist.

## Reviewer Results

All nine tracks passed after repairs. Details are in
`WS-ART-001-03B-PLAN-internal-review-evidence.md`.

## External Review

CodeRabbit reached its review-rate limit before producing findings. Agent Gates
found and prompted repair of five retired-vocabulary occurrences. The first
Backend run had one unrelated existing AUTH concurrency failure after 1,651
passes. Disposition is recorded in
`WS-ART-001-03B-PLAN-external-review-response.md`; repaired-head hosted checks
and CodeRabbit review remain required.

## Remaining Risks And Follow-Up

- 03B3B cannot start until exact pinned parser dependencies are approved.
- Images provide metadata only; image text requires a future OCR capability.
- Immediate post-merge implementation successor is 03B1.

## Human Review Focus

Confirm the upload separation, five-PR split, AUTH-04B placement, PostgreSQL
canonical extraction records, v0.1 format boundary, and dependency approval gate.

## Human Merge Ownership

A maintainer must explicitly approve this planning PR. Merge starts no
implementation automatically.
