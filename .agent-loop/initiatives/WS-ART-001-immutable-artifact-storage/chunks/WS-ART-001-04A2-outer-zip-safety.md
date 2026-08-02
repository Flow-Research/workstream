# Chunk Contract: WS-ART-001-04A2 — Bounded Outer-ZIP Safety

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04A1

## Goal

Accept one outer ZIP into canonical private scratch and safely enumerate its
complete file/directory tree without provider I/O or a public route.

## Allowed Files

ART scratch intake/archive safety capability, bounded configuration use,
adversarial ZIP tests/fuzz fixtures, docs, and scoped coverage evidence.

## Not Allowed Changes

Semantic manifest/change comparison, project checker, durable admission,
provider I/O, nested archive extraction, larger limits, or AUTH activation.

## Acceptance Criteria

Reject non-ZIP/additional items, traversal/absolute/UNC/backslash/control paths,
symlink/special/encrypted/malformed entries, duplicates/NFC/case-fold
collisions, bombs, and every configured limit breach; nested ZIPs stay opaque;
all outcomes clean scratch and disclose no path/handle.

## Verification Commands

Focused archive/scratch/fuzz tests, Ruff, stale scans, hosted gates, 90% owned
subsystem and 78% repository coverage.

## Required Reviewers

Security, architecture, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

No unchecked byte may escape scratch and no declared ZIP size is trusted.
