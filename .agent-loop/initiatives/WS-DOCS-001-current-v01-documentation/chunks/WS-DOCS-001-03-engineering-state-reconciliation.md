# Chunk Contract: WS-DOCS-001-03 Engineering State Reconciliation

## Intent

Make current engineering state discoverable without treating historical review
evidence or transient branch prose as repository truth.

## Allowed Files

- `AGENTS.md`
- `CONTRIBUTING.md`
- `docs/roadmap_status.md`
- `.agent-loop/README.md`
- `.agent-loop/CURRENT_STATE.md`
- `.agent-loop/REVIEW_LOG.md`
- `.agent-loop/initiatives/README.md`
- initiative `STATUS.md`, `CHUNK_MAP.md`, and `REVIEW_LOG.md` files whose
  current-facing state contradicts merged GitHub history
- this chunk contract and its review evidence

## Not Allowed

- Product or runtime code
- CI workflows, tests, coverage floors, dependencies, or package commands
- Canonical product architecture or lifecycle semantics
- Deletion or rewriting of historical review evidence
- Static claims that a transient branch or pull request is active

## Acceptance Criteria

1. One current-state entry page distinguishes merged capability truth,
   initiative disposition, transient pull requests, and historical reviews.
2. Contributor and agent entry paths link to that page and explain how to claim
   work without planning artifacts becoming authorization gates.
3. Every `REVIEW_LOG.md` is visibly archive-only.
4. Known stale initiative states are reconciled to merged PR history.
5. Markdown links, stale-wording checks, and diff integrity pass.

## Risk And Review

- Risk: L1 documentation and engineering-process navigation
- Required review: docs, senior engineering, and reuse/deduplication
- Add QA review because incorrect initiative disposition can misroute work

## Verification

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```
