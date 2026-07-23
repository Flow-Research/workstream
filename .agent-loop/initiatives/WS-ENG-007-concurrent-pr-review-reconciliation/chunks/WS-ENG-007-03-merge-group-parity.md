# Chunk Contract: WS-ENG-007-03 - Merge-Group CI Parity

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Run required policy and backend checks on GitHub's exact merge-group tree and
prove repository readiness before a human administrator enables merge queue.

## Risk class

L1 / required CI and merge admission

## Start phase

`implementation`

## Allowed files

```text
.github/workflows/agent-gates.yml
.github/workflows/backend.yml
AGENTS.md
.agent-loop/policies/repository-engineering-policy.md
docs/operations_post_merge_memory.md
scripts/workstream_agent_gate.py
scripts/check_internal_review_evidence.py
scripts/reconcile_review_base.py
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/STATUS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-03-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-03-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-03-external-review-response.md
.agent-loop/merge-intents/WS-ENG-007-03.json
```

## Not allowed

- Enabling merge queue or changing branch protection from repository code.
- Renaming, removing, skipping, or weakening required checks, tests, coverage,
  services, or human approval.
- Trusting a pull-request head check for a different merge-group SHA.

## Acceptance criteria

- [ ] Both required workflows support `merge_group` and retain pull-request and
      trusted-main behavior.
- [ ] `agent-gates` and final `test` contexts run on and bind the exact
      `github.sha` merge-group commit/tree. PR-head success never satisfies a
      group, and no group success is reused across another group SHA.
- [ ] Synthetic evidence binds queue base SHA plus ordered PR-head inputs. First group and
      recomputed successor groups after member merge, removal, or update are
      distinct. For disjoint PRs the eventual final tree may match across
      orderings, but every intermediate group SHA/tree and evidence record is
      independently bound and never reused.
- [ ] Required context names are exactly `agent-gates` and terminal `test` for
      pull request and merge group, with no event-only path filter, conditional,
      continue-on-error, skipped-success, shard/fan-in, or coverage weakening.
- [ ] Every `github.event.pull_request.*` use, checkout ref/SHA, concurrency
      group/cancellation, permission, secret, service, artifact, shard-plan,
      API-E2E, coverage-combine, and failure-propagation path is audited for
      merge-group payload safety.
- [ ] Workflows/jobs have read-only minimum permissions, no
      `pull_request_target`, no write token or secret exposed to checked-out
      code, and immutable action pins.
- [ ] Backend shards, API E2E, coverage combine, global 78 percent, and every
      protected 90 percent floor remain unchanged and blocking.
- [ ] Repository-side static and synthetic tests prove two concurrent PR
      orderings preserve required-check parity without bypass or duplicate
      internal reviewer fanout for disjoint changes.
- [ ] Human-admin enablement steps, rollback, and required-check verification
      are documented; the chunk itself does not mutate repository settings.
- [ ] YAML parsing/topology tests and negative fixtures cover missing trigger,
      renamed/duplicate/spoofed context, PR-only conditional/payload field,
      concurrency collision, cancelled/skipped/recomputed group, skipped fan-in,
      partial shard success, stale group SHA, and coverage artifact omission.
- [ ] The chunk claims repository-side readiness only. After merge, a separately
      authenticated human administrator may enable queue, generate real groups
      for both orderings, verify exact contexts/SHAs, and immediately disable on
      mismatch. Workflow code has no setting or merge authority.
- [ ] No tests/checks are deleted, skipped, xfailed, deselected, weakened, or
      replaced by mocks; required contexts and coverage floors cannot change.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
python3 -c 'from scripts.test_agent_gates import test_merge_group_workflow_parity; test_merge_group_workflow_parity()'
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 -c 'import pathlib, yaml; [yaml.safe_load(p.read_text()) for p in map(pathlib.Path, [".github/workflows/agent-gates.yml", ".github/workflows/backend.yml"])]'
git diff --check origin/main...HEAD
```

## Required reviewers

- [ ] senior engineering
- [ ] QA/test
- [ ] security/auth
- [ ] product/ops
- [ ] architecture
- [ ] CI integrity
- [ ] docs
- [ ] reuse/dedup
- [ ] test delta

## Human review focus

Do required checks bind the exact queue tree, and is administrative queue
enablement still a separate explicit human action?

## Stop conditions

Stop if required context parity, exact merge-group identity, or safe rollback
cannot be proven.
