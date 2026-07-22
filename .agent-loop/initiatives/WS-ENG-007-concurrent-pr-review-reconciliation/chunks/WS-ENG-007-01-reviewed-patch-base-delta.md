# Chunk Contract: WS-ENG-007-01 - Reviewed Patch and Base-Delta Reconciliation

## Parent initiative

`WS-ENG-007` — Concurrent PR Review Reconciliation

## Goal

Replace ancestry-only internal-review invalidation with deterministic patch
identity and conservative, track-aware base-advance reconciliation.

## Risk class

L1 / engineering merge integrity

## Start phase

`implementation`

## Allowed files

```text
AGENTS.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/templates/INTERNAL_REVIEW_EVIDENCE.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
.agent-loop/policies/review-boundaries.json
.agent-loop/schemas/review-base-reconciliation.schema.json
scripts/git_tree_evidence.py
scripts/update_post_merge_memory.py
scripts/check_internal_review_evidence.py
scripts/reconcile_review_base.py
scripts/test_agent_gates.py
scripts/test_git_tree_evidence.py
scripts/test_update_post_merge_memory.py
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/STATUS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-01-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-01-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-01-external-review-response.md
.agent-loop/merge-intents/WS-ENG-007-01.json
```

## Not allowed

- Workflow, branch-protection, merge-queue, product, backend, migration,
  coverage, or human-approval changes.
- Preservation based only on path disjointness, timestamps, PR prose, chat, or
  an unrecorded AI judgment.
- Automatic preservation when objects, boundaries, or classification are
  missing or ambiguous.

## Acceptance criteria

- [ ] One shared Git evidence module independently recomputes repository,
      reviewed trusted-main commit/tree, unique merge base, reviewed head/tree,
      object types/modes/OIDs, candidate base/tree, and effective delta; copied
      PR-authored hashes are never accepted as proof.
- [ ] Canonical JSON uses UTF-8, sorted keys, compact separators, SHA-256, and
      raw-path-sorted records containing path, add/delete/modify operation,
      old/new mode, and old/new blob OID. Renames are delete plus add.
- [ ] Symlink, executable, binary, empty, delete, and directory/file transitions
      preserve exact Git identities. Submodule, unsupported type, duplicate or
      invalid path, multiple base, missing/pruned object, and forged identity
      fail closed.
- [ ] Extracting shared Git primitives leaves existing loop-memory manifests,
      deltas, signed input payloads, generated projections, schemas, lifecycle,
      and authority behavior byte-for-byte unchanged across existing fixtures.
      Reconciliation is not a pre-merge dependency of post-merge memory, and a
      shared-helper failure fails closed independently in both consumers.
- [ ] A repository-owned versioned boundary graph derives path classes and
      transitive track impacts. Unknown path/class/edge, cycle, ambiguity,
      version drift, or omitted indirect dependency invalidates all potentially
      affected tracks; PRs cannot narrow it.
- [ ] Exact three-tree reconciliation constructs the candidate without context
      fuzz. Latest-main-to-candidate records must exactly equal the original
      base-to-head records. Upstream absorption, empty patch, changed output,
      or conflict invalidates.
- [ ] Identical effective patch plus provably unaffected boundaries may preserve
      only unaffected internal tracks.
- [ ] Changed patch, conflict, overlap, dependency-boundary impact, missing
      object, forged digest, or unknown classification invalidates fail closed.
- [ ] Legacy evidence remains valid only under today's exact-head rule and can
      never preserve review across a base advance. New malformed, extra,
      missing, duplicate/unknown track, foreign repository/initiative/chunk,
      or mismatched candidate evidence fails closed and prior review evidence
      cannot be rewritten in place.
- [ ] Synthetic histories cover merge, rebase, squash-equivalent, unrelated,
      overlapping, deleted-object, conflict, and indirect-boundary cases.
- [ ] Required CI still reruns on the latest combined tree, and human approval
      is never synthesized or preserved by this gate.
- [ ] The synthetic matrix expects `preserve` only for a truly disjoint base
      addition with identical patch/boundaries. It expects invalidation for
      same-path same/different result, upstream delete/rename/mode/binary change,
      conflict, multiple base, PR merge/rebase/squash ancestry with unequal
      trees, missing object, forged identity/digest, indirect dependency,
      workflow/generated-contract/migration impact, empty/already-applied patch,
      and text-similar but tree-different output. Every case asserts exact
      impacted tracks; unknown invalidates all potentially affected tracks.
- [ ] No tests/checks are deleted, skipped, xfailed, deselected, weakened, or
      substituted for real Git-object proof.

## Verification commands

```bash
python3 scripts/test_agent_gates.py
python3 scripts/test_git_tree_evidence.py
python3 scripts/test_update_post_merge_memory.py
python3 scripts/reconcile_review_base.py --validate-fixtures
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
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

Can any base change preserve a reviewer when the effective patch or dependency
boundary changed? Does every uncertain case invalidate safely?

## Stop conditions

Stop if deterministic patch reconstruction or conservative boundary impact
cannot be proven from immutable Git evidence.
