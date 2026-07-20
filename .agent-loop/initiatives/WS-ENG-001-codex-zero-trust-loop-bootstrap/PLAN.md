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

After 04A merge/replay and a separate user start, define a signed start event,
protected human-triggered workflow, exact-successor/current-main checks, active
projection rendering, and fail-closed stale/replay/conflict behavior.

### Alternatives and verification

Do not generate narrative histories, write protected `main`, or automatically
activate merge-intent successors. Use isolated state-root fixtures to prove
rendering, signature coverage, ledger reduction, exact cleanup, idempotency,
hostile path handling, and workflow permissions/order.
