# Planning Contract: WS-ART-001-03B - Guide Content Pipeline Expansion

Initiative: `WS-ART-001` | Risk: L1 | Status: Superseded by reviewed subchunks before implementation

Artifact contract phase: `guide_source_cutover`

## Goal

Preserve the original 03B intent while dividing binding, verified
materialization, isolated extraction, and sufficiency continuation into bounded
implementation contracts.

## Executable Subchunks

- `WS-ART-001-03B1`: authoritative binding and setup generation;
- `WS-ART-001-03B2`: verified materialization, incidents, and classification;
- `WS-ART-001-03B3A`: isolated framework and low-complexity extraction;
- `WS-ART-001-03B3B1`: pinned dependency approval and CI gate;
- `WS-ART-001-03B3B2`: PDF extraction;
- `WS-ART-001-03B3B3A`: shared OOXML container security;
- `WS-ART-001-03B3B3B`, `WS-ART-001-03B3B3C`, and
  `WS-ART-001-03B3B3D`: separate DOCX, PPTX, and XLSX extraction;
- `WS-ART-001-03B3B4`: image metadata extraction;
- `WS-ART-001-03B4`: same-generation Celery and sufficiency integration.

Each subchunk is one PR. AUTH `WS-XINT-002-04B` activates fixed binding/read
only after all five hidden ART contracts merge. ART-03C remains a later clean
cut.

## Shared Non-Goals

- contributor submission/checker/review behavior;
- direct provider access, URL fetching, a second scratch manager, parsing in the
  upload request, submission prechecks, OCR, audio/video transcription, or
  destructive legacy-field removal;
- AUTH-owned catalogue/evaluator/grant/identity/matrix/availability edits.

## Acceptance Criteria

- all five contracts merge before AUTH-04B;
- agents receive only same-generation canonical extracted material;
- artifact failures remain distinct from guide insufficiency;
- fixed guide read/binding remain unavailable until AUTH-04B;
- production parser dependencies require explicit human approval.

## Evidence

The five executable contracts own their exact file scopes, tests, coverage, and
review evidence. This umbrella is planning context and authorizes no code.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
