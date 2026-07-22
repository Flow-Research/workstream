# Chunk Contract: WS-ENG-007-02 - Finding and Reviewer-Track Reconciliation

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Record internal findings structurally and determine whether trusted upstream
changes resolve them, leave them valid, or require targeted reviewer reruns.

## Risk class

L1 / review authority and audit evidence

## Start phase

`implementation`

## Allowed files

```text
AGENTS.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/templates/INTERNAL_REVIEW_EVIDENCE.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
.agent-loop/schemas/review-finding.schema.json
scripts/check_internal_review_evidence.py
scripts/reconcile_review_base.py
scripts/test_agent_gates.py
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/STATUS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-02-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-02-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-02-external-review-response.md
.agent-loop/merge-intents/WS-ENG-007-02.json
```

## Not allowed

- Treating CodeRabbit or mutable GitHub comments as canonical internal evidence.
- AI-only automatic finding closure without a deterministic predicate.
- Synthesizing human approval or skipping CI.
- Workflow, merge-queue, product, backend, or coverage changes.

## Acceptance criteria

- [ ] Each finding has a stable ID, reviewer track, severity, immutable target
      evidence, closed predicate enum, and computed disposition. IDs are
      content-derived SHA-256 values with collision rejection.
- [ ] Reconciliation returns exactly `still_valid`, `resolved_upstream`,
      or `unknown`; `unknown` deterministically produces lifecycle state
      `track_stale` and reruns the owning/all affected tracks.
- [ ] Predicates are limited to `blob_equals`, `blob_absent`, `mode_equals`,
      `path_absent`, and repository-owned typed `diagnostic_absent`. Arbitrary
      commands, code, expressions, regex, URLs, comments, and claimant-authored
      dispositions are rejected.
- [ ] All predicates are resolution predicates: true means resolved and false
      means still valid. Per-predicate tests cover true/false on original,
      trusted-main, and candidate trees; equals-on-missing is false,
      absence-on-unambiguous-missing is true, and rename/recreation, evaluator
      error, or identity ambiguity is unknown and stales the track.
- [ ] Upstream resolution cites trusted-main commit/tree and deterministic proof.
- [ ] `resolved_upstream` requires an immutable original finding, trusted-main
      change to its bound target, true predicate in the exact candidate, and no
      contradictory/cross-track finding. A fix on main reintroduced by the PR
      remains `still_valid`.
- [ ] Unaffected tracks remain valid while impacted tracks rerun and produce new
      evidence bound to the candidate combined tree.
- [ ] Cross-track, renamed-path, deleted-target, dependency, forged-record, and
      contradictory-finding tests fail closed. Duplicate IDs, recreated targets,
      evaluator failure, PR-authored `resolved_upstream`, and evidence copied
      across repository/initiative/chunk return `unknown` and stale tracks.
- [ ] Track identifiers are exactly `senior engineering`, `QA/test`,
      `security/auth`, `product/ops`, `architecture`, `CI integrity`, `docs`,
      `reuse/dedup`, and `test delta`; aliases, spelling, or case drift fails.
- [ ] No test deletion, skip/xfail/deselection, assertion weakening, coverage
      reduction, or replacement of combined-tree proof with mocks is allowed.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
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

Can an upstream change falsely close a finding or preserve the wrong track?

## Stop conditions

Stop if finding resolution requires mutable conversation or unbounded semantic
judgment.
