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

1. Extend the append-only ledger with a closed event union for `merge`, `start`,
   `cancel`, and one 04B `cutover` record. Start/cancel events bind the dispatcher,
   environment approval reviewer(s), immutable workflow run ID and creation
   time obtained from the GitHub API, validated reason, protected-main SHA,
   initiative, chunk, and prior signed-state tip. Do not use runner wall time or
   rewrite earlier records.
2. Reduce events per initiative. `start` changes only the exact recorded
   same-initiative successor from `stopped_after_merge` to `active`; `cancel`
   returns that same chunk to the stopped explicit-start gate. Correction uses
   an attributable corrective cancellation followed by a fresh start.
3. Extend the existing repository-owned reconciliation, reducer, render,
   signing, exact-tree, and fast-forward commands; do not create a second
   start-specific state path. Before applying an authority event, authenticate
   state and reconcile every unrecorded protected-main merge through the exact
   expected SHA using the existing commit planner. Re-resolve protected `main`
   after environment approval and immediately before signing/push; fail if it
   moved. A failed/raced push leaves the branch unchanged and recovery uses a
   fresh dispatch after inspecting signed state.
4. Add `.github/workflows/loop-memory-start.yml` using `workflow_dispatch` only.
   Require ref `main`, `run_attempt == 1`, an exact expected current-main SHA,
   the fixed `loop-memory-start` protected environment, permissions of exactly
   `actions: read` and `contents: write` with all others absent/none, the shared
   non-cancelling concurrency group, credential-free
   checkout of independently resolved current main, and the fixed
   `automation/loop-memory` fast-forward destination. Parsed-YAML tests must
   reject every additional trigger, permission, ref, or destination path.
5. Treat a distinct required environment reviewer as authorization and the
   dispatcher as attribution. Disable self-review and administrator bypass;
   fetch and validate workflow-run approval history from GitHub and sign both
   identities. Reuse the existing `LOOP_MEMORY_SIGNING_KEY` identity already
   used by trusted merge memory; the environment gates the authority job rather
   than introducing or transferring another key. The key is never an
   input/argument/log/artifact value, uses a mode-0600 temporary file only if
   necessary, and is removed on every exit. Validate actor/reason IDs, lengths,
   Unicode/control characters, and the closed event type before use.
6. The 04B merge records a signed cutover and an exact reviewed inventory of
   initiative/chunk exemptions already in flight. Each exemption permits one
   merge-only closure and is consumed in signed state. After cutover, reject
   every no-active merge not in that inventory. Active initiatives must merge
   their exact signed chunk.
7. Update policy, skill, AGENTS, and operations guidance with exact environment
   settings and evidence, inputs/validation, audit lookup, the grandfather
   inventory, fresh-dispatch recovery, failure meanings, state-branch recovery,
   and signing-key rotation/compromise handling.
8. Prove event/schema reduction, deterministic rendering, signing, replay,
   stale/conflict rejection, cancel/retry, active-merge mismatch, failure
   atomicity, hostile paths, and exact workflow structure. Extend the required
   Agent Gates PR job with hash-pinned test/coverage dependencies and enforce at
   least 90 percent branch coverage independently for materially changed
   `update_post_merge_memory.py` and `check_loop_memory_state.py`, without
   weakening any existing CI gate.

### Alternatives and verification

Do not generate narrative histories, write protected `main`, or automatically
activate merge-intent successors. Use isolated state-root fixtures to prove
rendering, signature coverage, ledger reduction, exact cleanup, idempotency,
hostile path handling, and workflow permissions/order.
