# Chunk Contract: WS-CI-004-01 — Review Target Protocol

## Merge state

- Outcome on merge: `complete`

## Goal

Add the shared reviewer-evidence protocol, its canonical receipt schema, and one
small deterministic read-only command that identifies an exact Git review
target. Do not adopt the protocol in reviewer agents yet.

## Why this chunk exists

Reviewer adoption must depend on one tested subject and receipt contract rather
than nine prompts inventing their own revision, dirty-state, or evidence fields.

## Risk class

L1 / P1 — engineering review trust infrastructure.

## Allowed files

```text
.agents/skills/reviewer-evidence-protocol/SKILL.md
scripts/git_delta.py
scripts/review_target.py
scripts/test_review_target.py
.agent-loop/templates/INTERNAL_REVIEW_EVIDENCE.md
.agent-loop/templates/REVIEW_FINDING.md
.agent-loop/templates/INTERNAL_REVIEW_RECEIPT.schema.json
.agent-loop/initiatives/WS-CI-004-review-evidence-integrity/**
.agent-loop/CURRENT_STATE.md
```

## Not allowed

```text
.codex/agents/**
existing specialty review skills
.github/workflows/**
hosted receipt storage or validation
receipt writer or convergence orchestration
GitHub API or network calls
signing, starts, leases, merge intent, recovery, active queue, or merge authority
product/runtime/API/schema/migration code
new dependencies
```

## Acceptance criteria

- The protocol defines exact target, clean-worktree finality, evidence
  provenance, stable findings, uncertainty, freshness, and closed verdicts.
- `scripts/review_target.py` reuses `scripts/git_delta.py` and emits deterministic
  JSON containing resolved base, merge base, head, changed paths/statuses, and
  tracked/staged/unstaged/untracked cleanliness.
- `review_target.py` uses checked Git calls for target resolution and cleanliness;
  empty output from a failed command cannot mean valid, unchanged, or clean.
  Changes to `git_delta.py` must preserve its existing public behavior and must
  not duplicate Git-resolution semantics in the new command.
- Invalid base/head refs, refs that are not commits, unrelated histories,
  merge-base failure, Git nonzero/timeout, non-repository execution, and empty
  helper output fail closed with stable non-zero exits and a stable error shape.
- Cleanliness means no staged, unstaged, or non-ignored untracked paths. Fixtures
  cover clean, staged, unstaged, untracked, base drift, rename, deletion, invalid
  refs, and a local change after inspection start. Dirty state remains observable
  but cannot report `final_ready` or a final `PASS`; start/end target or
  cleanliness mismatch invalidates finality.
- The canonical JSON schema defines target, reviewer/run identity, evidence,
  findings/dispositions, uncertainty, start/end inspection, and verdict fields.
- Target fields require 40-hex SHAs. Verdict, severity, disposition, evidence
  kind, cleanliness, and freshness use closed enums. Security-sensitive objects
  reject additional properties. Custody is explicitly advisory/session-only;
  executed and inspected evidence are distinct and never authorize execution.
- Schema tests validate a minimal good receipt and reject malformed JSON,
  unknown verdicts/results, missing target or run identity, malformed SHAs,
  missing uncertainty or start/end inspection, unresolved blocking findings,
  unsupported evidence claims, and extra authority-like fields.
- Existing Markdown templates reference the schema and distinguish advisory
  session receipts from durable GitHub evidence.
- At runtime the review-target command writes no receipt/session/product file,
  mutates no repository state, calls no network, and authorizes no work or merge.
- Implementation remains below 450 non-test Python lines; otherwise stop and
  split after human review.

## Verification commands

```bash
python3 -m unittest -v scripts.test_review_target
python3 -m unittest -v scripts.test_git_delta scripts.test_lightweight_agent_gates
python3 scripts/review_target.py --base origin/main --head HEAD --format json
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_chunk_state_sync.py --base-ref origin/main
git diff --check
```

## Required reviewers

Architecture, security, QA/test, CI integrity, senior engineering,
documentation, reuse/dedup, and test delta.

## Human review focus

Confirm this is a small read-only sensor and shared contract—not a receipt
custodian, hosted gate, contribution authority, or orchestration engine.

## Stop conditions

Stop if implementation requires credentials, network access, mutable review
state, a workflow change, another Git-delta implementation, or product behavior.
