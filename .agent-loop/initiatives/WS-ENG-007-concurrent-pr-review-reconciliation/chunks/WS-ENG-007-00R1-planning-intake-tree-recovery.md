# Chunk Contract: WS-ENG-007-00R1 - Planning-Intake Tree Recovery

## Parent initiative

`WS-ENG-007` - Concurrent PR Review Reconciliation

## Goal

Restore signed planning-intake reconciliation by comparing reviewed files with
recursive non-tree Git entries, then recover PR #187 and this repair exactly
once without weakening ordinary start enforcement.

## Why this chunk exists

PR #187 merged at `8928ba80eeaf31e609dbdeda7d2cc22e9ea482c8`, but both automatic
post-merge memory and a fresh
explicit start failed closed. GitHub's recursive tree response includes newly
created directory objects; GitHub PR file evidence and the independent local
checker correctly enumerate recursive non-tree paths. The updater therefore
compares 19 tree entries with 13 reviewed files and rejects a valid intake.

## Risk class

L1 / P0 engineering authority recovery

## Start phase

`implementation`

## Bootstrap authority

This otherwise-unstartable repair uses the existing reviewed schema-v1 exact
two-merge recovery mechanism. The immutable recovery certificate must name only
PR #187 (`WS-ENG-007-PLAN`, merge
`8928ba80eeaf31e609dbdeda7d2cc22e9ea482c8`) and activation chunk
`WS-ENG-007-00R1`. The target repair must be the direct next first-parent merge,
all required checks must pass, both exemptions must be consumed before signing,
and neither exemption may persist in signed state or ledger history.

## Allowed files

```text
.agent-loop/policies/loop-memory-recovery.json
scripts/update_post_merge_memory.py
scripts/test_update_post_merge_memory.py
scripts/test_agent_gates.py
scripts/test_check_loop_memory_state.py
docs/operations_post_merge_memory.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/CHUNK_MAP.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/STATUS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/RISKS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/DECISIONS.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/chunks/WS-ENG-007-00R1-planning-intake-tree-recovery.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-00R1-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-00R1-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-007-concurrent-pr-review-reconciliation/reviews/WS-ENG-007-00R1-external-review-response.md
.agent-loop/merge-intents/WS-ENG-007-00R1.json
```

## Not allowed

- Manual or unsigned edits to `automation/loop-memory`.
- Workflow, signing-key, permission, environment, branch-protection, product,
  backend, coverage, or human-approval changes.
- Ignoring blobs, symlinks, executables, gitlinks, modes, OIDs, or silently
  discarding any unsupported non-tree object.
- Wildcard, multi-target, persistent, reusable, identity-ambiguous, or
  non-consuming recovery authority.
- Starting `WS-ENG-007-01` or `WS-ENG-006-01` inside this repair.

## Acceptance criteria

- [ ] GitHub recursive tree collection first validates top-level shape,
      `truncated is false`, every item's path/SHA/mode/type, duplicates, and
      prefix structure. Exact `tree`/`040000` directory entries may prefix
      descendants and are validated as directory ancestors. A retained
      non-tree leaf may never be an ancestor of another retained entry (`a`
      blob/commit plus `a/b` fails closed). Only after complete validation may
      exact directory entries be excluded from the canonical leaf map; no
      stronger ancestor-presence invariant is inferred beyond the API's
      validated complete response.
- [ ] The generic complete-tree map accepts and retains only exact supported Git
      pairs: `blob` with `100644`, `100755`, or `120000`, and `commit` with
      `160000`; `tree` with `040000` is validated then excluded. Every other
      kind/mode pair fails closed. Planning-intake delta policy independently
      requires each changed entry to be `blob`/`100644`, so changed executable,
      symlink, gitlink, unsupported non-tree, deletion, or transition evidence
      cannot enter a planning intake even though unchanged supported repository
      leaves remain representable.
- [ ] A real-shaped fixture with an absent initiative directory proves the
      reviewed and merged non-tree deltas equal the exact PR file inventory;
      directory entries cannot appear in `changed_paths` or its digest.
- [ ] Negative fixtures cover malformed directory SHA/mode/path; `040000` blob;
      non-`040000` tree; `160000` blob; commit with wrong mode; changed gitlink,
      executable, and symlink; unknown kind; duplicate path; a leaf-prefix
      collision such as `a` plus `a/b`; truncation; malformed SHA; deletion;
      duplicate/malformed PR filename or status; extra/missing PR evidence; and
      changed merge output.
- [ ] Directory/file transition fixtures cover both directions with descendants:
      file-to-directory deletes the leaf and adds descendant leaves;
      directory-to-file deletes every descendant and adds the leaf. Directory
      objects never enter `changed_paths` or the canonical delta digest.
- [ ] Exact set equality holds among GitHub PR filenames, reviewed non-tree
      delta paths, and merged non-tree delta paths, and the complete
      path-to-mode/type/OID-or-delete maps are equal. The regression fixture
      reproduces the pre-fix 19-entry versus 13-file failure and passes only
      after directory exclusion.
- [ ] Existing planning-intake schema, grammar, required-check provenance,
      successor, stopped-state, additive-only, and independent-checker tests
      remain unchanged and blocking.
- [ ] Named golden fixtures freeze representative non-planning canonical merge
      records, manifest, ledger entry, signing input/payload, state, queue, and
      initiative projections and remain byte-for-byte unchanged. The corrected
      planning-intake fixture intentionally adds exactly the recovered PLAN and
      00R1 records/projections without changing schemas or serialization.
- [ ] Recovery policy names only PR #187 merge
      `8928ba80eeaf31e609dbdeda7d2cc22e9ea482c8` as
      `WS-ENG-007-PLAN` and activation `WS-ENG-007-00R1`; the ordered plan must
      contain exactly those two adjacent first-parent merges.
- [ ] Trusted GitHub evidence uniquely attributes PR #187 and 00R1 and binds
      exact base/first-parent, reviewed head/tree, merge tree, merge intent, and
      foreign-file exclusion. PR #187 must retain its recorded aggregate
      required-check success; 00R1 must additionally pass the existing exact
      protected GitHub Actions provenance check. Direct push, ambiguous or
      duplicate PR attribution, wrong head/base/tree, and foreign delta fail.
- [ ] The recovery certificate is loaded only from the exact reviewed 00R1
      activation tree. Its inventory exists only in bounded ephemeral workflow
      custody, is consumed before signing on success, never serializes into
      generated state or ledger, and retry/error/partial-consumption paths fail
      without publishing. Recovery persists neither exemption and rejects replay,
      collision, wrong/later target, intervening merge, partial consumption,
      wrong order, missing/extra SHA, independent failure of either merge's
      required checks, and every foreign identity.
- [ ] A recovered planning record passes the independent loop-state checker;
      mutations to `changed_paths`, digest, tree SHAs, or lifecycle identity
      fail. Existing updater/checker schema and rendering parity remains exact.
- [ ] The final signed projection records 00R1 stopped with
      `WS-ENG-007-01` as explicit-start successor. It also records the recovered
      planning intake without activating implementation.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-007-01` as the same-
      initiative explicit-start successor.
- [ ] 00R1 retains the ordinary specific-PR human merge approval, internal
      reviewer fanout, CodeRabbit, Agent Gates, and Backend requirements.
      Recovery substitutes only for the impossible predecessor signed start.
- [ ] This is a minimal local repair of the existing planning collector and
      existing recovery validator/preparer. It adds no second parser or
      authority path; `WS-ENG-007-01` still owns extraction into the shared
      `scripts/git_tree_evidence.py` module without semantic change.
- [ ] The operations runbook records the root cause, full recovered SHA, exact
      two-merge order, asymmetric recovered/activation check provenance,
      temporary consumption-before-signing, inert replay, and that both
      `WS-ENG-007-01` and `WS-ENG-006-01` remain stopped pending their own
      ordinary explicit signed starts.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_update_post_merge_memory.py scripts/test_agent_gates.py scripts/test_check_loop_memory_state.py
python3 scripts/test_agent_gates.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
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

Does the fix remove only directory objects from file identity, retain every
security-relevant non-tree object, and make the recovery exact, adjacent,
self-consuming, and impossible to reuse?

## Stop conditions

Stop if repair requires a manual state edit, force push, new secret, workflow or
authority weakening, a non-exact recovery exemption, or if another main merge
lands before this exact recovery target.
