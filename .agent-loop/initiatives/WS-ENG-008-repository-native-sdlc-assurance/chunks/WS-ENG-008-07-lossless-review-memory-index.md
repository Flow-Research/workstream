# Chunk Contract: WS-ENG-008-07 — Lossless Review Memory Index

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Replace the growing root review narrative with a compact index while preserving
every historical byte, link, and initiative-owned detailed evidence.

## Why this chunk exists

The 147 KB root log is expensive for agents to load and duplicates detailed
initiative review files, but it remains widely referenced durable memory.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Start phase

`implementation`

Execution remains blocked until this planning intake is merged, chunks 01–06
are completed in order, and the explicit post-merge signed start selects this
exact contract from current trusted `main`.

## Allowed files

```text
.agent-loop/README.md
.agent-loop/REVIEW_LOG.md
.agent-loop/review-log-archive/**
.agent-loop/policies/repository-engineering-policy.md
scripts/check_review_log_archive.py
scripts/test_check_review_log_archive.py
scripts/check_loop_memory_state.py
scripts/check_stale_artifact_contracts.py
scripts/check_markdown_links.py
scripts/check_stale_workstream_wording.py
scripts/test_agent_gates.py
AGENTS.md
CONTRIBUTING.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/STATUS.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-07-lossless-review-memory-index.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-07-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-07-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-07-pre-migration-reconciliation.json
.agent-loop/merge-intents/WS-ENG-008-07.json
```

## Not allowed

```text
deletion, paraphrase, deduplication, reorder, or silent correction of historical review entries
generated automation-branch schema or signed-state changes
application, API, database, product lifecycle, workflow permission, test, or coverage weakening
migration while another reviewed/open PR still writes root REVIEW_LOG.md without exact reconciliation
automatic successor declaration
```

## Acceptance criteria

- [ ] Discovery re-fetches all open PRs and current main immediately before the
      migration; every root-log delta is reconciled or the chunk stops. A
      durable pre-migration JSON snapshot records the fetch timestamp, exact
      main SHA, every open PR number and head SHA, root-log SHA-256 digest, and
      explicit reconciliation result.
- [ ] Versioned archive files preserve the complete pre-migration root narrative
      byte-for-byte in one documented concatenation order with stored SHA-256
      digests and deterministic reconstruction.
- [ ] Root `REVIEW_LOG.md` becomes a bounded index linking archive periods,
      initiative review directories, current conventions, and reconstruction
      proof. Its complete UTF-8 encoding, including every newline byte, is at
      most 32,768 bytes.
- [ ] Historical repository links remain valid or receive an explicit lossless
      mapping; no initiative evidence file is rewritten merely for relocation.
- [ ] New detailed review evidence remains initiative-owned; root additions are
      compact navigation rather than duplicate narrative.
- [ ] Checker rejects missing/extra/reordered bytes, digest mismatch, broken
      links, duplicate periods, path traversal, symlink, an index over 32,768
      UTF-8 bytes including newline bytes, or a reconciliation snapshot whose
      main/PR heads/root digest do not bind the migrated input.
- [ ] Existing stale-contract and authored-memory checks understand the index
      without weakening their semantic rules.
- [ ] Exactly one schema-v2 merge intent declares no successor.

## Verification commands

```bash
python3 scripts/test_check_review_log_archive.py
python3 scripts/check_review_log_archive.py
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

- Can the exact old root log be reconstructed without relying on Git history?
- Are current navigation and future ownership clearer and bounded?
- Was every concurrent root-log writer reconciled immediately before merge?

## Stop conditions

Stop if any history cannot be preserved byte-for-byte, links cannot be mapped,
or concurrent PRs still carry unresolved root-log changes.
