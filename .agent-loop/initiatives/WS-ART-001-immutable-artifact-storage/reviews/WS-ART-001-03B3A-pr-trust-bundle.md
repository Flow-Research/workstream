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

The pre-rebase focused extraction and architecture suite passed locally,
including real outside-scratch write denial and stale workspace crash recovery.
After rebasing onto merged AUTH-12A, Ruff, Python compilation, single-head
migration inspection, stale-contract scan, Markdown links, and diff integrity
pass. Refreshed focused and PostgreSQL proof remains delegated to hosted CI
because this worktree's incomplete test environment resolves a conflicting
global pytest plugin. CodeRabbit's valid findings and the first hosted database-test
failures were repaired without weakening a workflow, threshold, or assertion.
The isolated worker now also has additive parent-process unit coverage while
its real kernel-isolation subprocess probes remain unchanged.
The migration chain has one head at `0042_guide_extraction`; exact hosted
Backend and Agent Gates remain required on the refreshed PR head before merge.

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
