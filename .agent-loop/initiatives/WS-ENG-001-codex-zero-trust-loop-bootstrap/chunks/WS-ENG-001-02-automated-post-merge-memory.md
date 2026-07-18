# Chunk Contract: WS-ENG-001-02 - Automated Post-Merge Memory

## Parent Initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Replace manual post-merge memory PRs and repeated reviewer fanout with a
deterministic GitHub workflow that records merged PR state on a dedicated
automation branch.

## Human-Approved Intent

The user explicitly requested this process repair after PR #119 merged. A
manager should review the implementation PR once; generated post-merge
bookkeeping must not require another human or internal-agent review.

## Risk Class

L1 - CI and engineering-process infrastructure.

## Allowed Files

```text
AGENTS.md
.agents/skills/memory-update/SKILL.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
.agent-loop/merge-intents/**
.agent-loop/keys/**
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/**
.github/pull_request_template.md
.github/workflows/agent-gates.yml
.github/workflows/loop-memory.yml
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
```

## Not Allowed

```text
backend/**
frontend/**
database schema or migrations
Workstream product behavior
authentication or authorization runtime behavior
coverage thresholds
existing lint, test, or review gates for implementation PRs
direct automated writes to main
automated PR approval or merge
execution of pull-request-head code with write credentials
```

## Design Boundary

- `main` remains protected and human-approved.
- The workflow runs only trusted code already merged to `main`.
- Generated state is written to `automation/loop-memory`, not `main`.
- Organization policy disables deploy keys, so the workflow signs every
  canonical generated file with an Actions-only Ed25519 private key and
  verifies the signature before trusting existing branch state. Final
  verification also binds state to the protected-main target; invalid branch
  state is discarded and rebuilt from the immutable bootstrap.
- One newly added, immutable merge-intent JSON file supplies bounded chunk and
  next-gate metadata from the reviewed PR head.
- This chunk's immutable merge intent anchors empty-state bootstrap; the first
  successful run reconciles from that activation commit through its target.
- The updater validates repository, base branch, merge SHA, intent schema,
  check conclusions, idempotency, and monotonic merge history.
- Missing, modified, duplicate, or malformed merge intent fails closed; the
  updater never derives authority state from mutable PR prose.
- Generated state updates are process output, not implementation chunks, and
  are exempt from reviewer fanout only on the dedicated automation branch.

## Acceptance Criteria

- [ ] A push to `main` reconciles every unrecorded first-parent commit through
      its target SHA on `automation/loop-memory`.
- [ ] The state branch contains canonical JSON, rendered Markdown, an
      append-only JSONL merge ledger, and a valid signature over all three.
- [ ] Replaying the same merge is idempotent.
- [ ] An older merge cannot replace newer live state.
- [ ] Missing/malformed PR metadata, wrong repository/base/SHA, or ambiguous
      associated PRs fail closed; missing or failed checks are recorded as
      attention required rather than misreported as passing.
- [ ] The workflow has no pull-request-head checkout and no write to `main`.
- [ ] Workflow permissions are limited to contents, pull requests, checks, and
      commit statuses; generated state is signed and verified with the reviewed
      public key before branch data is trusted.
- [ ] PR templates require one newly added machine-readable merge-intent file.
- [ ] Agent policy removes manual post-merge PR/reviewer requirements when the
      canonical automation succeeds.
- [ ] A documented manual retry exists for workflow/operator failure.
- [ ] Unit tests cover parsing, immutable intent binding, validation, replay,
      first-parent reconciliation, full-ledger integrity, rendering, pending
      reruns, and workflow integrity.
- [ ] Existing internal-review, coverage, lint, and product gates are not
      weakened.

## Verification Commands

```bash
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format markdown
git diff --check
```

## Required Reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human Review Focus

- The automation branch is the only write target.
- The workflow never executes untrusted PR-head code with a write token.
- The metadata parser and merge/check validation fail closed.
- The exception applies only to generated post-merge state, not implementation
  or specification PRs.

## Stop Conditions

- Any design requires bypassing `main` protection.
- The workflow needs a personal access token or unpinned third-party action.
- The change weakens implementation PR review, test, or coverage gates.
- The updater cannot prove one exact merged PR and successful required checks.
