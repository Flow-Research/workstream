# External Review Response: WS-ART-001-02A3

## Current State

- Pull request: #141, open and not draft
- Reviewed implementation SHA: `c8eccaafb6b4f0615b1b37049edfcb0368dd6fb2`
- Latest published SHA before this response: `cdeef292b8137cf8c48cc040d82f1a93dffa4d2c`
- Prior GitHub and CodeRabbit results predate required AUTH/CON main
  reconciliation and are not completion evidence for the current candidate
- Latest repaired SHA external checks: pending publication
- Human merge approval: pending

Internal sub-agent review is recorded only in the separate internal-review
evidence. This file records CodeRabbit, GitHub, and later human PR feedback.

## CodeRabbit Findings Addressed

| Finding | Status | Response |
|---|---:|---|
| Local layout marker was not published atomically. | Fixed | Marker bytes are written and fsynced through a private temporary, installed with an exclusive hard link under a root lock, and recovered only through the exact validated one-link or same-inode two-link states. |
| Stored upload states admitted partial result metadata. | Fixed | Model and migration require both `content_id` and `provider_object_ref` for stored states and require both null otherwise. |
| Independent upload items were fenced by a shared session CAS. | Fixed | Provider I/O is fenced by the item attempt; finalization locks and validates the current open session without requiring an unchanged session CAS. |
| Reservation accounting silently clamped drift. | Fixed | Both counters are validated before exact subtraction; inconsistent accounting raises `ArtifactIntegrityError`. |
| Downgrade proof did not reject leftover v2 columns. | Fixed | Migration tests assert every v2-only replica, upload, receipt, and namespace column is absent after downgrade. |
| Architecture checks matched provider method names globally. | Fixed | The AST gate now follows `ArtifactStore` typed receiver provenance instead of unrelated `put`, `open`, or `head` calls. |
| Scratch-worker import gate ignored plain imports. | Fixed | Both `ast.Import` and `ast.ImportFrom` are inspected. |
| Test settings cache could leak temporary worker configuration. | Fixed | Cache teardown is registered as a test finalizer. |
| Concurrent fake acknowledgements used mutable arrival state. | Fixed | Each call snapshots its arrival number before the barrier. |
| Failure-path assertions did not prove handler exclusivity. | Fixed | Each branch asserts its required handler once and the alternate handler never. |
| Cutover gate test passed the old phase literal. | Fixed | Both scans use `gate.ARTIFACT_CONTRACT_PHASE`, which is `artifact_store_cutover`. |
| Focused commands and cumulative gates measured different source sets. | Fixed | Active and future ART commands include their exact owned operations/core sources; deterministic gate tests pin the workflow commands and cumulative retention. |
| Removed `provider_manifest_id` was absent from migration proof but not the ORM test. | Fixed | The active-model clean-cut test explicitly rejects the field. |
| A `#139` line could be parsed as a malformed heading. | Fixed | The PR reference is attached to normal prose. |

## Finding Not Applied

CodeRabbit's generic pre-merge widget reported 62 percent docstring coverage
against an 80 percent default. The repository's authoritative configured
docstring gate is 92.0 percent and passes. Lowering or duplicating that gate
would weaken the repository contract, so no change was made for the generic
widget warning.

## Validation After Repairs

```text
73 filesystem/architecture/wiring tests: PASS
59 final LocalStorage/conformance tests: PASS
9 critical real PostgreSQL orchestration tests: PASS
5 migration-chain tests, including 4 clean-cut safety tests: PASS
ART exact scoped coverage: 93.31%
Ruff: PASS
Repository docstring gate: 92.0%, PASS
Stale artifact/authorization/Workstream scans: PASS
Markdown links: PASS
Agent gates: 80 PASS
All nine exact-SHA internal reviewer tracks: PASS
Open sub-agent sessions: none
```

GitHub must rerun the isolated full repository suite, 78 percent whole-app
floor, all cumulative scoped 90 percent gates, and real API drill on the newly
published evidence-bound head.

## Remaining External Gate

Push the evidence-only descendant, wait for GitHub Actions and CodeRabbit on
that head, address every still-valid new finding, and stop for the user's
explicit merge decision. Do not start `WS-ART-001-02B1` automatically.
