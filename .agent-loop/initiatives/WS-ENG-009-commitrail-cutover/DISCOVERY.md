# WS-ENG-009 Discovery — Commitrail Cutover

## Observed repository state

- `.agent-loop` occupies approximately 9.4 MB and contains 1,246 initiative
  files across 33 initiative directories, 76 merge-intent files, 16 template
  files, and 12 policy files.
- `.agent-loop/CURRENT_STATE.md` is the current durable initiative ledger.
  GitHub open pull requests are already defined as the transient-work view.
- `.agent-loop/README.md` already rejects the directory as an authorization
  database and recommends the smallest useful artifact.
- Git history preserves every removed record after cutover.

## Direct dependencies outside `.agent-loop`

### Contributor and architecture guidance

- `AGENTS.md`, `CONTRIBUTING.md`, and `README.md`
- `docs/architecture_lockdown.md`
- `docs/operations_post_merge_memory.md`
- `docs/operations_subagent_review_protocol.md`

### Skills and reviewer configuration

- `.agents/skills/initiative-planning/SKILL.md`
- `.agents/skills/task-chunk-loop/SKILL.md`
- `.agents/skills/plan-to-chunks/SKILL.md`
- `.agents/skills/memory-update/SKILL.md`
- `.agents/skills/external-review-response/SKILL.md`
- `.agents/skills/reviewer-evidence-protocol/SKILL.md`
- `.codex/agents/product-ops-reviewer.toml`
- `.codex/config.toml`

### Automation and tests

- `.github/workflows/agent-gates.yml` runs atomic chunk-state and active-state
  projection validators tied to `.agent-loop`.
- `scripts/check_chunk_state_sync.py` requires one changed chunk contract and
  synchronized `CHUNK_MAP.md`, `STATUS.md`, and `CURRENT_STATE.md` projections.
- `scripts/check_active_state_projections.py` scans the current-state file.
- `scripts/reviewer_contracts.py` binds reviewer adoption wording to it.
- Regression tests under `scripts/` encode those paths and behaviors.
- `.github/pull_request_template.md` mirrors an `.agent-loop` template.

### Product and operational references

Current documents cite selected handoffs, action custody, conformance, and
historical contracts under `.agent-loop`, including:

- `docs/spec_authorization_service.md`
- `docs/spec_review_lifecycle.md`
- `docs/spec_contribution_compensation.md`
- `docs/operations_roles_permissions.md`
- `docs/operations_authorization_service.md`

These references must be classified as normative, current navigation, or
historical evidence. Normative facts must move to the owning specification or a
current Commitrail decision record; historical-only links must be labelled or
removed rather than copied wholesale.

## Existing checks to preserve

- Markdown link checking
- Workstream and authorization stale-wording checks
- Artifact-contract stale checks
- Reviewer contract and exact-target review tests
- Backend test and coverage workflows
- Human approval and conversation-resolution protections on GitHub

## Worktree integration risk

At discovery time, separate worktrees exist for ARCH, AUTH, and CON branches.
They may contain `.agent-loop` changes based on the old method. The cutover must
not edit those worktrees. Their owners must rebase after cutover and translate
their still-current intent into one Commitrail change record rather than
restoring `.agent-loop`.

## Gaps

- The generated Commitrail v0.1 source currently exists outside the repository
  and has no repository-owned canonical location or assigned public license.
- There is no automated negative assertion that legacy engineering-method
  paths cannot return.
- Current initiative truth is spread across verbose status files and must be
  distilled against `docs/roadmap_status.md` and current specifications.

## Assumptions

- The user intends removal from the current working tree, not destruction of
  Git history.
- Commitrail will initially be a Workstream-owned repository method; public
  licensing and an independent upstream repository may follow separately.
