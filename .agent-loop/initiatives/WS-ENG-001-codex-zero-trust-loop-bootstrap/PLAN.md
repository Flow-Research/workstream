# PLAN: WS-ENG-001

## Approach

Bootstrap Workstream's engineering loop using Codex-native surfaces first:

1. Keep `AGENTS.md` as the hard repository instruction layer.
2. Add `.agents/skills/` for Codex-discoverable workflow skills.
3. Add `.codex/agents/` for read-only custom reviewer agents.
4. Add `.agent-loop/` for durable policies, initiative memory, templates, review
   logs, and chunk contracts.
5. Add CI/static gates that strengthen existing evidence requirements.
6. Add a PR template based on the trust bundle pattern.

## Design Choices

- `.agents/skills/` is canonical for Codex skills because Codex scans that path.
- `.agent-loop/` is canonical for engineering memory because it should be readable
  by humans and portable across repositories.
- `.agent-loop/skills` is intentionally not used to avoid duplicated skill sources.
- Claude files are excluded because this repo is being optimized for Codex CLI.
- Product/Ops review is first-class because Workstream is operational
  infrastructure, not only code.

## Alternatives Rejected

- Blindly copying the entire kit: rejected because it would import Claude files,
  generic TODOs, and duplicate skill locations.
- Keeping everything only in docs: rejected because Codex would not discover
  skills or custom reviewer agents directly.
- Relying only on CodeRabbit and CI: rejected because Workstream requires
  internal reviewer tracks before external review is considered sufficient.

## Verification Strategy

- Compile Python gate scripts.
- Run the Workstream agent gate against `origin/main...HEAD`.
- Run the internal review evidence gate.
- Run stale wording scan.
- Run Markdown link check for changed Markdown files.
- Run required internal reviewer tracks and record findings.

## 2026-07-20 Projection Consistency Plan

### 04A: complete post-merge projections

1. Define `.agent-loop/MANIFEST.json` as the ordered generated-file manifest.
2. Reduce the authenticated ledger to latest stopped/next state per initiative.
3. Render loop state, work queue, and compact initiative projections at
   `.agent-loop/INITIATIVE_STATE/<initiative-id>.md`, ordered lexicographically,
   from the same typed data. Label them merge-derived stopped/next projections,
   not narrative or complete live-work histories.
4. Include the complete projection manifest in the signature domain.
5. Authenticate the existing canonical state, generate into a newly created
   empty output directory, construct a new tree from an empty temporary Git
   index containing only the manifest paths, validate it, and commit it as a
   normal child of the existing branch tip. Do not delete or traverse legacy
   worktree paths and do not force-push.
6. Independently reproduce and compare every projection byte-for-byte.
7. Preserve trusted-main execution, fixed push destination, concurrency, and
   protected-main freshness.
8. Resolve protected `main` at replay time and prove the generated latest merge,
   completed chunk, stopped gate, and successor exactly match that target's
   immutable merge intent and check evidence. Retain AUTH-09E/ART-custody and
   ART-custody/REV-custody transitions as historical fixtures rather than a
   hard-coded live target.

### 04B: authenticated explicit starts

After 04A merge/replay and a separate user start:

1. Extend the append-only ledger with a closed schema-v2 event union for
   `merge`, `start`, and `cancel`. Start/cancel events bind GitHub actor, unique
   workflow run ID, event time, reason, protected-main SHA, initiative, chunk,
   and prior signed-state tip. Do not rewrite earlier records.
2. Reduce events per initiative. `start` changes only the exact recorded
   same-initiative successor from `stopped_after_merge` to `active`; `cancel`
   returns that same chunk to the stopped explicit-start gate. Correction uses
   an attributable corrective cancellation followed by a fresh start.
3. Add repository-owned commands that apply a validated event to an already
   authenticated state root, rerender the complete closed tree, sign it, and
   validate it with the existing manifest/tree boundary.
4. Add `.github/workflows/loop-memory-start.yml` using `workflow_dispatch` only.
   Require ref `main`, `run_attempt == 1`, an exact expected current-main SHA,
   the fixed `loop-memory-start` protected environment, minimal read/write
   permissions, the shared concurrency group, reviewed code from current main,
   and the fixed `automation/loop-memory` fast-forward destination.
5. Keep the signing key environment-scoped. Treat environment approval and
   GitHub actor attribution as the human authority; never accept chat text,
   feature-branch code, arbitrary successors, or caller-selected destinations.
6. When merge reconciliation encounters an active initiative, require the
   merged chunk to equal that active chunk before clearing it. Preserve
   merge-only handling for work already in flight when 04B deploys.
7. Update policy, skill, AGENTS, and operations guidance with dispatch, cancel,
   recovery, environment setup, audit, and rollout rules.
8. Prove event/schema reduction, deterministic rendering, signing, replay,
   stale/conflict rejection, cancel/retry, active-merge mismatch, hostile paths,
   and workflow permissions/order. Preserve at least 90 percent branch coverage
   for materially changed loop-memory scripts.

### Alternatives and verification

Do not generate narrative histories, write protected `main`, or automatically
activate merge-intent successors. Use isolated state-root fixtures to prove
rendering, signature coverage, ledger reduction, exact cleanup, idempotency,
hostile path handling, and workflow permissions/order.
