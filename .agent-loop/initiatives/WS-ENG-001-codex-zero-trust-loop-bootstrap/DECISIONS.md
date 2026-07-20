# DECISIONS: WS-ENG-001

## Accepted

- Use `.agents/skills/` for repo-scoped Codex skills.
- Use `.codex/agents/` for Codex custom reviewer agents.
- Use `.agent-loop/` for durable engineering memory and evidence.
- Do not copy Claude-specific files into Workstream in this bootstrap.
- Add Product/Ops as a first-class reviewer track.
- Preserve existing `docs/internal_reviews/` evidence compatibility.
- Treat the manager-approved implementation PR as the only human merge
  checkpoint. Post-merge state is deterministic process output, not another
  reviewable chunk.
- Store canonical live merge state on `automation/loop-memory` so protected
  `main` is never bypassed and generated bookkeeping needs no PR.
- Require one strict, newly added merge-intent JSON file in every reviewed PR
  rather than deriving chunk or next-gate intent from mutable prose, branch
  names, or chat history.
- Run the write-capable workflow only from trusted code already merged to
  `main`; never use `pull_request_target` or pull-request-head execution.
- Authenticate all generated state with an Actions-only Ed25519 key and a
  reviewed public key because organization policy disables deploy-key writer
  restriction for the automation branch.
- Scope a non-null merge-intent successor to the completed chunk's own
  initiative. Cross-initiative priority remains in human-owned planning and
  cannot be asserted by immutable post-merge metadata.
- Reject schema v1 everywhere and start the replacement signed ledger from the
  `WS-ENG-001-03` schema-v2 merge intent.
- Extend `WS-ENG-001` rather than create a parallel engineering-loop initiative.
- Split projection consistency (`04A`) from explicit-start events (`04B`) so
  merge completion and human start remain separate authorities.
- Derive automation-branch Markdown only from typed authenticated state; do not
  copy authored narrative files from `main` as live projections.
- Derive global initiative summaries from the latest authenticated ledger record
  per initiative, not from the single last-merge record alone.
- Keep manual post-merge memory PRs retired when automation succeeds.
- Store compact generated initiative projections under the dedicated
  `.agent-loop/INITIATIVE_STATE/<initiative-id>.md` namespace; never overwrite
  authored initiative `STATUS.md` histories.
- Use an ordered `.agent-loop/MANIFEST.json` containing every generated payload
  path and content digest. The manifest and `STATE.sig` are excluded from the
  manifest's self-referential entries. Validate the exact Git tree and safe file
  types first, then sign the manifest bytes followed by its ordered
  `(path, bytes)` payload entries; only `STATE.sig` is excluded from signature
  input.
- Migrate the legacy automation branch by creating a fresh exact tree from an
  empty temporary Git index and output directory, then make a normal
  fast-forward child commit. Do not recursively delete the cloned worktree and
  do not force-push.

## Deferred

- Packaging the loop as a reusable Codex plugin for other Flow projects.
- Adding hooks that block local PR creation before evidence exists.
- Automating reviewer fanout beyond Codex's explicit subagent workflow.
- Packaging generated-state storage behind a GitHub App or external service;
  the repository-scoped automation branch is sufficient for the current loop.
- Any external work-coordination registry beyond bounded signed start and
  cancel/correct events.
