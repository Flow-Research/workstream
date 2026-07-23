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
      evidence, closed predicate enum, and computed disposition. The ID is
      SHA-256 over compact sorted-key UTF-8 JSON with version
      `workstream-review-finding-id-v1` and exactly repository, initiative,
      chunk, canonical reviewer track, repository-owned rule ID, and target.
      Target binds raw path, target kind, immutable original object or
      diagnostic key, predicate kind, and immutable expected value. Severity,
      wording, disposition, changing evidence, timestamps, reviewer session,
      and rerun results are excluded. A duplicate digest with a different
      canonical payload rejects the complete evidence set. An exact duplicate
      payload/ID is also rejected as duplicate evidence and returns `unknown`
      with every track stale.
- [ ] Reconciliation returns exactly `still_valid`, `resolved_upstream`,
      or `unknown`; `unknown` deterministically produces lifecycle state
      `track_stale` for every track. Targeted reruns are permitted only when
      path, class, edge, and transitive impact are all deterministically known.
- [ ] Predicates are limited to `blob_equals`, `blob_absent`, `mode_equals`,
      `path_absent`, and repository-owned typed `diagnostic_absent`. Arbitrary
      commands, code, expressions, regex, URLs, comments, and claimant-authored
      dispositions are rejected.
- [ ] All predicates are resolution predicates: true means resolved and false
      means still valid. Per-predicate tests cover true/false on original,
      trusted-main, and candidate trees; equals-on-missing is false,
      absence-on-unambiguous-missing is true, and rename/recreation, evaluator
      error, or identity ambiguity is unknown and stales every track.
- [ ] `diagnostic_absent` binds checker repository path, checker blob OID,
      declared checker version, diagnostic code, and SHA-256 digests of its
      input and output schemas. Candidate evaluation records the same identity;
      any checker, version, or schema mismatch is `unknown` and stales every
      track.
- [ ] Upstream resolution cites trusted-main commit/tree and deterministic proof.
- [ ] `resolved_upstream` requires an immutable original finding, trusted-main
      change to its bound target, true predicate in the exact candidate, and no
      linked non-resolved or contradictory finding. Findings link only on the
      same repository, initiative, chunk, raw path, target kind, and original
      object or diagnostic code key; unrelated findings never block.
      Distinct expected blob OIDs or modes, absence versus equality, or distinct
      checker/schema identities for one diagnostic code are contradictions.
      Linked-set evaluation is atomic: all true and contradiction-free resolves
      every member; any false without unknown/contradiction makes every member
      `still_valid`; any unknown, contradiction, or cross-track disagreement
      makes every member `unknown` and stales all tracks. A fix on main
      reintroduced by the PR remains `still_valid`.
- [ ] Unaffected tracks remain valid while impacted tracks rerun and produce new
      evidence bound to the candidate combined tree.
- [ ] Cross-track, renamed-path, deleted-target, dependency, forged-record, and
      contradictory-finding tests fail closed. Duplicate IDs, recreated targets,
      evaluator failure, PR-authored `resolved_upstream`, and evidence copied
      across repository/initiative/chunk return `unknown` and stale tracks.
      Tests cover linked versus unrelated findings and every closed
      contradiction pair.
- [ ] Canonical-ID tests prove field/key insertion order yields byte-identical
      compact sorted-key UTF-8 JSON and digest; changing each included field,
      including version and every nested target field, changes the ID; changing
      every excluded mutable field does not. Missing, extra, duplicate-key,
      noncanonical track/path/value, invalid UTF-8, and non-JSON values fail
      closed. Exact duplicate payload/ID is rejected. An injected identical
      digest for non-byte-identical payloads rejects the complete evidence set;
      tests inject the digest result and never attempt a real SHA-256 collision.
- [ ] Linked-set tests cover all-true, all-false, true/false, true/unknown,
      false/unknown, every declared contradiction pair, and cross-track
      disagreement on same-track and different-track cases. They assert the
      atomic outcomes: all true resolves all; any false alone keeps all linked
      members `still_valid`; any unknown, contradiction, or cross-track
      disagreement returns `unknown` and stales all tracks. Exact duplicates
      follow the duplicate rejection rule, and unrelated findings never affect
      one another.
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
