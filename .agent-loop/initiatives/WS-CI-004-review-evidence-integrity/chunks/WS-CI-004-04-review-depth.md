# Chunk Contract: WS-CI-004-04 — Review Depth

## Merge state

- Outcome on merge: `complete`

## Goal

Make exact-head reviews prove impact-cone and adversarial inspection without
creating hosted receipt custody or another merge authority.

## Risk class

L1 — reviewer protocol and evidence schema.

## Allowed files

```text
.agents/skills/reviewer-evidence-protocol/SKILL.md
.agents/skills/pr-trust-bundle/SKILL.md
.codex/agents/*-reviewer.toml
.agent-loop/templates/INTERNAL_REVIEW_RECEIPT.schema.json
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/CHUNK_MAP.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/STATUS.md
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/chunks/WS-CI-004-04-review-depth.md
.agent-loop/CURRENT_STATE.md
scripts/reviewer_contracts.py
scripts/test_reviewer_contracts.py
scripts/test_review_target.py
```

## Not allowed

```text
product or runtime behavior
hosted or committed exact-head receipt custody
new merge gates or approval authority
universal reviewer fanout
automatic merge
```

## Acceptance criteria

- [ ] Final receipts name relevant unchanged owners, consumers, policies,
      boundaries, or ledgers and explain their relevance.
- [ ] Final receipts record at least one specialty-appropriate adversarial
      probe and its observed result; a final passing verdict requires at least
      one successful probe.
- [ ] The canonical schema rejects receipts missing either proof.
- [ ] Reviewer agents invoke the target sensor through `python3` at both review
      boundaries.
- [ ] Trust bundles distinguish skipped or rate-limited external status from
      fresh substantive review.
- [ ] Session receipts remain private and out of tree; PR summaries remain
      non-authoritative mirrors.

## Verification commands

```bash
python3 -m unittest -v scripts.test_review_target scripts.test_reviewer_contracts
python3 scripts/reviewer_contracts.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
python3 scripts/check_active_state_projections.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Required reviewers

Architecture, security, QA, CI integrity, senior engineering, reuse/dedup, and
documentation.

## Human review focus

Confirm the additional proof improves review depth without pretending local
session receipts are durable GitHub attestations.
