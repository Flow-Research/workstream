# Chunk Contract: WS-ENG-001-04A - Complete Loop Memory Projections

## Parent initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Make one trusted post-merge run atomically generate, sign, and independently
validate every canonical live merge projection so stale queue or initiative
status copies cannot disagree with signed state.

## Human-approved intent

The user explicitly started planning on 2026-07-20 after AUTH-09E PR #157
demonstrated that signed `STATE.json` and `LOOP_STATE.md` were current while
legacy automation-branch `WORK_QUEUE.md` and AUTH `STATUS.md` remained stale.
Manual post-merge memory PRs must remain retired.

## Risk route

- Risk class: L1
- SLA: P1
- Work type: architecture, infrastructure, CI/workflow, bug, test, docs
- Required reviewers: senior engineering, QA/test, security/auth, product/ops,
  architecture, CI integrity, docs, reuse/dedup, and test delta
- Human gate: approval before implementation and approval of the implementation
  PR before merge
- Budget posture: careful and proof-heavy; no product-runtime test expansion

## Allowed files

```text
AGENTS.md
.agents/skills/memory-update/SKILL.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/**
.agent-loop/merge-intents/WS-ENG-001-04A.json
.github/workflows/loop-memory.yml
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
```

## Not allowed

```text
backend/**
frontend/**
database schema or migrations
product authentication, authorization, artifact, review, contribution, or payment behavior
dependency or coverage-threshold changes
manual edits or force-pushes to automation/loop-memory
automated writes to main
pull-request-head execution with write credentials
explicit-start event implementation or automatic successor activation
cross-initiative priority selection
generated rewrites of narrative initiative planning/history
```

## Design boundary

- `STATE.json` and the authenticated append-only merge ledger remain typed
  authority.
- The generator reduces the ledger to the latest completion record per
  initiative for compact global projections.
- `LOOP_STATE.md`, `WORK_QUEUE.md`, and generated per-initiative status views
  are deterministic projections, not independent truth.
- `.agent-loop/MANIFEST.json` contains an ordered list of every generated payload
  path and content digest. Fixed payloads are `STATE.json`, `MERGE_LOG.jsonl`,
  `LOOP_STATE.md`, and `WORK_QUEUE.md`; initiative projections
  use `.agent-loop/INITIATIVE_STATE/<initiative-id>.md`, where the validated
  schema-v2 initiative ID is used verbatim and paths sort lexicographically.
  The exact committed tree is those payloads plus `MANIFEST.json` and
  `STATE.sig`; neither self-referential file appears as a manifest entry.
- Each initiative projection is headed `Generated Merge/Start Projection`,
  identifies its initiative, latest completed chunk, stopped gate, next chunk,
  explicit-start requirement, source merge, and authenticated source-event
  timestamp—never render wall-clock time—and warns that pre-04B
  conversational/unmerged starts are not represented.
- Tree validation first requires exactly the manifest-listed regular payloads
  plus `MANIFEST.json` and `STATE.sig`, with no symlinks, directories outside the
  fixed parents, or extra paths. Signature input commits to the manifest bytes followed by ordered
  `(path, bytes)` entries for every manifest payload; `STATE.sig` alone is
  excluded from signature input.
- The first migration authenticates existing canonical state, generates into a
  newly created empty output directory, builds a fresh tree from an empty
  temporary Git index containing only validated output, checks the written tree
  against the manifest, and commits it as a normal child of the prior state-
  branch tip. It neither traverses/deletes the legacy checkout nor force-pushes.
- After migration, unexpected tracked paths fail normal validation. The existing
  human-triggered replay is the recovery path: it reauthenticates retained
  canonical inputs and uses the same fresh-tree/normal-child-commit process.
- Merge projections show completed/stopped/next state only; 04B separately owns
  later explicit-start events.
- Trusted-main execution, fixed branch destination, serialized runs,
  protected-main freshness, and explicit human merge ownership are preserved.

## Acceptance criteria

- [ ] One merge produces mutually consistent signed JSON, ledger, loop state,
      work queue, and latest-per-initiative status projections.
- [ ] Every projection is reproduced byte-for-byte from authenticated typed
      state by generator and independent checker.
- [ ] Exact-tree validation fails on extra, missing, symlinked, or substituted
      paths; signature validation fails on changed content or ordered manifest
      disagreement.
- [ ] A closed exact-path manifest prevents stale authored queue/status copies
      from surviving on the automation branch.
- [ ] A fresh temporary index stages the complete replacement tree, including
      deletion of all 626-style legacy tracked paths, while preserving the prior
      commit as parent and leaving filesystem content outside the temporary
      output directory untouched.
- [ ] Interleaved merges preserve the latest record for each initiative while
      retaining the latest global merge.
- [ ] Historical fixtures prove AUTH-09E to ART custody and ART custody to REV
      custody transitions. Live replay resolves current protected `main` at run
      time and exactly matches its immutable merge intent/check evidence rather
      than a planning-time PR number.
- [ ] Replay is deterministic and requires no PR, reviewer fanout, or write to
      `main`.
- [ ] Existing schema-v2, signature, replay, freshness, concurrency, and check-
      evidence protections remain fail-closed.
- [ ] Existing implementation review, CI, coverage, branch protection, and
      human merge gates remain unchanged.
- [ ] Changed loop-memory scripts retain at least 90 percent branch coverage.

## Required regression tests

- interleaved initiatives reduce to one latest record per initiative;
- queue and initiative projections match exact renderers;
- stale AUTH-05B branch fixtures are removed and cannot validate;
- missing, extra, altered, reordered, symlinked, and hostile file types fail;
- fresh-tree migration drops legacy tracked paths and uses the prior tip as
  parent; writes stay inside fixed temporary index/output roots, branch-
  controlled reads are limited to fixed authenticated canonical inputs, trusted
  code/key and Git object/metadata reads remain allowed, and outside sentinels
  remain byte-for-byte unchanged;
- post-migration unexpected paths fail normal validation, and protected replay
  reconstructs a valid fast-forward child without a force-push;
- signature tampering in every projection fails;
- idempotent replay produces no new content;
- current-main reconciliation updates all projections atomically;
- workflow stages and commits the closed complete manifest only;
- workflow preserves trusted-main code, fixed push ref, serialized runs, least
  permissions, and no pull-request-head execution;
- merge output stays stopped and never fabricates an explicit start.

## Verification commands

```bash
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m coverage run --branch --source=scripts -m pytest -q scripts/test_agent_gates.py
python3 -m coverage report -m --include='scripts/update_post_merge_memory.py' --fail-under=90
python3 -m coverage report -m --include='scripts/check_loop_memory_state.py' --fail-under=90
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format markdown
git diff --check
```

## Human review focus

Closed generated/signature manifests, exact safe cleanup, latest-per-initiative
reduction, no false active claim, and no return to manual memory PRs or weakening
of protected-main/human gates.

## Stop conditions

- Correct projections require parsing mutable prose or chat history.
- Tree construction cannot be bounded to the fixed temporary index/output roots
  and the validated manifest.
- The signature cannot cover every canonical projection atomically.
- The workflow must write `main`, use a personal token, execute PR-head code, or
  weaken a required gate.
- Explicit-start behavior becomes necessary; stop and leave it to 04B.

## Required documentation changes

Update `AGENTS.md`, the memory-update skill, repository engineering policy, and
`docs/operations_post_merge_memory.md` to define the expanded manifest/signature
domain, authority precedence, projection namespace and stopped-state limitation,
normal replay, first migration, and unexpected-path recovery.

## Current gate

Planning and required internal specification review only. Do not implement
until the user explicitly approves this reviewed contract.
