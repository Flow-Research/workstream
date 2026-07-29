# PR Trust Bundle: WS-ART-001-03B3A

## Chunk

`WS-ART-001-03B3A` — Extraction Framework And Text Formats (L1)

## Goal And Intent

Extract bounded canonical text from exact verified guide content without
weakening artifact custody or allowing raw binaries, provider access, or caller
authority to cross into the parser boundary.

## What Changed

- Added a default-deny, resource-limited, descriptor-only extraction child.
- Added deterministic UTF-8 text/Markdown, strict JSON, and strict CSV
  canonicalization.
- Added immutable attempts, successful extracted content, exact usage, and a
  durable two-slot retry budget with composite database custody.
- Added extraction-specific scratch workspace custody and cleanup recovery.
- Added exact generation/classification revalidation and focused security,
  boundary, retry, migration, and provenance tests.

## Scope Control

No PDF/OOXML/image parser, provider write, agent invocation, Celery continuation,
public route, submission behavior, legacy cutover, or AUTH availability change
is included.

## Tests And CI Integrity

Focused extraction and architecture tests pass locally. Ruff, mapper setup,
static migration rendering, stale-contract scan, Markdown links, and diff
integrity pass. No workflow or coverage threshold was weakened. Exact hosted
Backend and Agent Gates remain required before review publication.

## Internal Review

All required L1 reviewer tracks pass after repairs. Details are in the paired
internal review evidence.

## Remaining Boundary And Next Gate

The feature remains hidden. `artifact.guide_source.binding.create` and
`artifact.guide_source.read` remain planned and unavailable. ART-03B3B is the
same-initiative successor and requires a separate explicit start after merge.

## Human Review Focus

Confirm default-deny parser isolation, exact lineage locks, two-slot retry
custody, successful-attempt usage fencing, and absence of provider/agent/AUTH
scope expansion. The user retains merge approval for this PR.
