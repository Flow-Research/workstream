# WS-ART-001-03B3B3A PR Trust Bundle

## Chunk

`WS-ART-001-03B3B3A` — OOXML Container Security (L1).

## Goal and human-approved intent

Install only the previously approved `defusedxml` dependency and add a shared,
bounded OPC/OOXML security boundary for verified guide-source bytes. Project
Manager guide uploads remain distinct from contributor submission ZIPs. This
chunk must not extract DOCX/PPTX/XLSX content or activate AUTH or sufficiency.

## What changed and why

- Added the exact hash-bound `defusedxml==0.7.1` wheel and lock evidence.
- Added central-directory-first OOXML validation with exact format markers,
  passive package-part/content-type/relationship policies, and bounded XML.
- Reused the classifier's canonical limits, markers, and EOCD facts so
  classification and child validation cannot drift.
- Added a typed isolated-worker loader that maps every security failure to the
  existing bounded extraction protocol without registering an adapter.
- Assigned focused tests to `shared_foundations` and documented the boundary.

## Design chosen and alternatives rejected

The existing format classifier owns server classification and shared ZIP facts;
the isolated child owns `defusedxml` parsing and strict OOXML validation. Future
DOCX, PPTX, and XLSX adapters must pass this boundary before semantic parsing.
Rejected alternatives were upload-time parsing, root-only allowlists, filename-
only active-content checks, direct provider access, generic ZIP support, and
activating incomplete document adapters.

## Scope control and product behavior

The corrected contract lists every changed implementation, test, lane, and
documentation file. There is no route, provider, binding, AUTH, Celery,
submission, review, payment, reputation, or agent-input behavior. Malformed,
ambiguous, active, external, or over-limit packages become bounded internal
extraction outcomes, never guide-insufficiency decisions.

## Acceptance criteria proof

- All metadata is inspected before any body read; a spy proves zero reads for
  encrypted, duplicate, unsafe-path, unknown/cross-format, marker-conflict,
  special-entry, and executable metadata failures.
- Exact 2,000/2,001 entry, central-directory, decompressed-byte, compression,
  and relationship-size boundaries are covered.
- Symlinks, traversal, encryption, ZIP64/multidisk, nested/prefixed archives,
  macros, embeddings, executables, DTD/entities including UTF-16, active MIME
  or relationship metadata, and external/escaping targets reject fail closed.
- Only the exact classified format root and passive OPC parts are accepted;
  directory entries cannot satisfy required file markers.
- Corrupt local headers and body reads map to stable bounded failures.

## Tests and checks

- Ruff, dependency gate, and lock check — pass.
- Focused OOXML/extraction/classification/architecture suite — 136 passed.
- OOXML module coverage — 93.92 percent.
- CI lane inventory — 31 passed.
- Stale-contract scan, Markdown links, and `git diff --check` — pass.
- Hosted Backend/Agent Gates retain repository-wide coverage and semantic-lane
  proof; no local full-suite run was used.

## Test delta and CI integrity

No test, assertion, lane, workflow, or coverage threshold was removed, skipped,
or weakened. The new focused module is in the existing `shared_foundations`
lane. The dependency is an exact approved PyPI wheel URL/hash and the lockfile
resolves the same bytes.

## Reviewer results

Architecture, security, QA, senior engineering, CI integrity, docs, and test
delta pass. Product/ops and reuse/dedup pass with non-blocking future advice.
Initial strictness, metadata, DTD, nested-archive, reuse, and assertion findings
were repaired and re-reviewed.

## External review

CodeRabbit found one valid non-canonical root-relationship base issue. Root
relationships are now restricted to `_rels/.rels`, malformed relationship-part
shapes fail closed, and focused regressions cover the repair. Its generic
docstring warning is superseded by the passing repository-owned hosted gate.
Hosted GitHub Backend/Agent Gates must pass again on the repaired PR head.

## Remaining risks and follow-up

OOXML is a complex untrusted container, so isolated execution and the strict
positive policy remain essential. The later 03B3B3B/C/D chunks add document-
specific extraction separately; 03B3B4 handles image metadata. AUTH remains
planned/unavailable until the complete hidden 03B series merges.

## Human review focus and merge ownership

Review the exact dependency hash, central-directory-first ordering, passive
part/content-type/relationship policies, shared classifier facts, stable
failure mapping, and absence of adapter activation. A human owns merge approval;
the agent will not merge this PR.
