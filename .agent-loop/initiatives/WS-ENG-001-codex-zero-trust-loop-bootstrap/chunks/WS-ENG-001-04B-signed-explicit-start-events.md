# Chunk Contract: WS-ENG-001-04B - Signed Explicit Start Events

## Parent initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Record a protected human start as authenticated loop state and regenerate the
same canonical projections without a bookkeeping PR or automatic successor
activation.

## Risk routing

- Risk class: L1
- SLA: P1
- Work type: architecture, CI/workflow, signed authority, audit ledger,
  documentation, and tests
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, and test delta
- Human gate: required before implementation, protected-environment deployment,
  PR review, and merge
- Budget posture: proof-heavy; start authority, state signatures, and workflow
  credentials require complete fail-closed evidence

## Preconditions

- `WS-ENG-001-04A` merged and replay proved all projections consistent.
- A separate explicit human start approved 04B implementation.
- Preimplementation review resolves the deferred actor authorization,
  environment protection, event schema, and mandatory signed cancel/correct
  semantics for mistaken, rejected, or abandoned starts.

## Allowed files

```text
AGENTS.md
.agents/skills/memory-update/SKILL.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/policies/loop-memory-legacy-start-exemptions.json
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/**
.agent-loop/merge-intents/WS-ENG-001-04B.json
.github/workflows/loop-memory-start.yml
.github/workflows/loop-memory.yml
.github/workflows/agent-gates.yml
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
scripts/test_update_post_merge_memory.py
scripts/test_check_loop_memory_state.py
scripts/agent-gate-requirements.txt
```

## Not allowed

Product runtime, schema/migrations, automatic start after merge, arbitrary or
cross-initiative selection, chat-derived authority, PR-head execution with
write credentials, direct `main` writes, automated PR approval/merge, or start
of a second chunk while the same initiative is active.

## Acceptance criteria

- Only a protected, attributable human workflow event can start work.
- The requested chunk equals the signed same-initiative successor and its exact
  contract exists on current protected `main`.
- The event signs dispatcher attribution, distinct environment-approver
  authorization, immutable workflow-run ID and API creation time, protected-main
  SHA, prior state tip, initiative, chunk, and validated reason.
- Identical replay is non-mutating; same-ID/different-byte collision, duplicate
  run, stale main/tip, invalid identity/reason, null/wrong/cross-initiative
  successor, already-active start, and wrong/inactive cancellation fail closed.
- All canonical projections update atomically and identify the active chunk.
- A later trusted merge closes that exact active chunk and returns the
  initiative to a stopped successor gate.
- Merge completion must match the authenticated active chunk before clearing it.
- An attributable protected human cancel event records reason and evidence,
  resists replay, and deterministically returns active state to the same
  successor gate without rewriting history.
- No manual bookkeeping PR is required.
- Start and cancel use a `workflow_dispatch` workflow selected from `main`, run
  only on `refs/heads/main`, with `run_attempt == 1`, shared serialization, a
  fixed state-branch destination, and the protected `loop-memory-start`
  environment.
- The protected job reuses the existing `LOOP_MEMORY_SIGNING_KEY`; no second key
  is generated, transferred, or stored. It is never accepted as input/argv or
  exposed in logs/artifacts, uses mode-0600 temporary storage only when
  required, and is removed on exit.
- Correction is an attributable corrective cancellation restoring the same
  successor gate, followed by a separate protected start; arbitrary replacement
  is absent.
- A legacy merge-only closure requires an exact initiative/chunk in the signed
  cutover inventory and consumes that exemption once. Every other post-cutover
  no-active merge fails; active state must merge its exact chunk.
- Before start/cancel, signed state catches up every unrecorded merge through the
  expected main SHA. Main is resolved again after environment approval and
  immediately before signing/push; movement fails closed.
- Exact active merge closes; wrong active merge fails. Cancel then retry succeeds
  without history rewrite. Signature/tree/render/write/push failure and every
  rejected event leave canonical branch state unchanged.
- Parsed-YAML tests enforce the exact trigger, job-level main/first-attempt
  guard, environment, permissions of exactly `actions: read` and
  `contents: write` with all others absent/none, non-cancelling shared
  concurrency, credential-free trusted-main checkout, fixed push ref, and
  absence of caller-controlled ref/destination values.
- Before publication, GitHub settings/API evidence proves required reviewers,
  disabled self-review/admin bypass, and protected-main deployment restriction;
  a missing or misconfigured environment fails rollout.
- Materially changed `update_post_merge_memory.py` and
  `check_loop_memory_state.py` each remain at or above 90 percent branch
  coverage in the required Agent Gates PR job. Test/coverage dependencies are
  hash-pinned and no existing gate is weakened.

## Verification commands

```text
python3 -m pytest -q scripts/test_agent_gates.py
python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 -m pytest -q --cov=scripts.update_post_merge_memory --cov-branch --cov-report=term-missing --cov-fail-under=90 scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 -m pytest -q --cov=scripts.check_loop_memory_state --cov-branch --cov-report=term-missing --cov-fail-under=90 scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py
python3 scripts/check_loop_memory_state.py --state-root <fixture-root>
gh api repos/{owner}/{repo}/environments/loop-memory-start
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check
```

## Required reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, CI
integrity, docs, reuse/dedup, and test delta.

## Stop condition

Stop if protected environment review cannot gate the signing secret, current
protected `main` cannot be resolved independently, an event would select a
non-successor/cross-initiative chunk, cancellation would rewrite history, or
the required Agent Gates job cannot enforce each coverage floor. Also stop if
scope expands into product runtime, automatic merge, or another chunk.
