# Chunk Contract: WS-ENG-001-03 - Initiative-Local Loop Gates

## Parent Initiative

`WS-ENG-001` - Codex Zero-Trust Loop Bootstrap

## Goal

Correct automated post-merge memory so a merge intent may name only the next
chunk in its own initiative. Reconcile stale authored loop state on `main` and
cleanly rebootstrap signed schema-v2 state from this corrective chunk.

## Human-Approved Intent

The user explicitly approved an end-to-end correction after the first live
generated state exposed a cross-initiative next pointer from `WS-ENG-001-02` to
`WS-AUTH-001-06`. Parallel initiative priority remains a human-owned work-queue
decision; one merged chunk must not declare lifecycle authority for another
initiative.

## Risk Class

L1 - CI, signed engineering memory, and lifecycle authority infrastructure.

## Work Type

Architecture, CI, bug, test, docs, and engineering-process maintenance.

## Allowed Files

```text
AGENTS.md
.agents/skills/memory-update/SKILL.md
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/policies/repository-engineering-policy.md
.agent-loop/templates/PR_TRUST_BUNDLE.md
.agent-loop/merge-intents/WS-ENG-001-03.json
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/CHUNK_MAP.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/DECISIONS.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/RISKS.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/STATUS.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/chunks/WS-ENG-001-03-initiative-local-loop-gates.md
.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/reviews/WS-ENG-001-03-*.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/STATUS.md
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/CHUNK_MAP.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/STATUS.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md
.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/chunks/WS-ART-001-OBJECT-STORAGE-AMENDMENT.md
.github/pull_request_template.md
.github/workflows/agent-gates.yml
.github/workflows/loop-memory.yml
docs/operations_post_merge_memory.md
scripts/update_post_merge_memory.py
scripts/check_loop_memory_state.py
scripts/test_agent_gates.py
```

## Not Allowed

```text
backend/**
frontend/**
database schema or migrations
Workstream product lifecycle behavior
authentication or authorization runtime behavior
artifact storage runtime behavior
dependency changes
coverage threshold reductions
lint, test, evidence, approval, or branch-protection weakening
direct automated writes to main
general schema-v1 compatibility paths
manual edits to automation/loop-memory
```

## Design Chosen

- Future merge intents use schema version 2.
- `chunk_id` and non-null `next_chunk_id` must both belong to
  `initiative_id`.
- A null next chunk is valid and means that the completed initiative declares
  no successor. Global or parallel priority remains outside the merge intent.
- Schema v1 is rejected everywhere. There is no compatibility parser,
  normalizer, alias, or migration path.
- Existing signed schema-v1 generated state is intentionally invalid under the
  new validator. The trusted workflow clears only fixed generated paths and
  starts a new schema-v2 ledger at this corrective chunk's immutable merge
  intent, then reconciles later protected-main commits.
- Generator and independent checker both validate completed-chunk and gate
  agreement, initiative ownership, schema, rendering, and ledger history.
- Agent Gates require each non-null successor to resolve to exactly one
  chunk contract under the unique existing directory for the declared
  initiative whose canonical heading matches both successor ID and title.
  A second same-prefix initiative directory fails closed. Post-merge
  collection rechecks the same reviewed-head directory and contract.
- Trusted-main workflow execution resolves current protected `main` after
  checkout. A stale explicit replay target fails closed; a queued push event
  may reconcile forward only when its event SHA is an ancestor of current
  protected `main`.
- Authored `main` loop files are planning and historical context. Canonical
  post-merge state remains the verified signed state on
  `automation/loop-memory`; authored files must not retain merged PRs as active.

## Alternatives Rejected

- Keep one global `next_chunk_id`: rejected because parallel initiatives make
  it ambiguous and allow one initiative to claim another's lifecycle gate.
- Store a list of global next chunks in merge intent: rejected because global
  prioritization is mutable human planning, not immutable merged-chunk fact.
- Migrate or normalize PR #122 schema-v1 state: rejected because the generated
  ledger contains only one invalid entry and retaining it would add permanent
  compatibility logic without product value.
- Hand-edit signed state: rejected because generated branch ownership and
  signature provenance must remain intact.

## Acceptance Criteria

- [ ] New schema-v2 merge intents reject a cross-initiative `next_chunk_id`.
- [ ] A successor contract under any other initiative directory is rejected,
      even when its filename and heading claim the expected successor ID.
- [ ] Zero or multiple same-prefix directories for the declared initiative
      fail before successor lookup.
- [ ] Same-initiative and null next gates parse, persist, render, sign, verify,
      and replay deterministically.
- [ ] Every schema-v1 intent, state, ledger entry, and signature domain is
      rejected without migration or normalization.
- [ ] Existing signed schema-v1 state is rejected, only fixed generated files
      are cleared, and this chunk becomes the unique schema-v2 bootstrap.
- [ ] Generator and independent checker reject cross-initiative or mismatched
      next gates in live state and any ledger record.
- [ ] Workflow structural tests preserve trusted-main execution, fixed branch
      writes, freshness verification, and absence of bypass controls.
- [ ] A stale `repository_dispatch` target fails closed even when generated
      state is missing or invalid; a queued push target may only reconcile
      forward to the current protected-main SHA.
- [ ] Authored loop, initiative, and queue records no longer claim PR #119,
      PR #120, or PR #122 are pending or active.
- [ ] `WS-AUTH-001-06` and `WS-ART-001-02A1` remain separate inactive
      candidates requiring explicit human start; neither is selected globally
      by this engineering merge intent.
- [ ] Changed loop-memory scripts retain at least 90 percent branch coverage.
- [ ] Regression coverage starts from signed schema-v1 state containing the
      invalid cross-initiative successor, proves only fixed generated paths are
      cleared, starts from this schema-v2 bootstrap, verifies protected-main
      freshness, and passes the independent state checker.
- [ ] Regression coverage rejects cross-initiative successors in both live
      state and every ledger record, and rejects stale PR #119/#120/#122
      pending or active claims while preserving AUTH-06 and ART-02A1 as
      separate inactive candidates.
- [ ] Forward-looking documentation and templates use schema v2; schema v1 is
      mentioned only as rejected historical state.
- [ ] No Workstream product behavior, runtime, dependency, or gate threshold
      changes.

## Verification Commands

```bash
python3 -m py_compile scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m coverage run --branch --source=scripts -m pytest -q scripts/test_agent_gates.py
python3 -m coverage report -m --include='scripts/update_post_merge_memory.py' --fail-under=90
python3 -m coverage report -m --include='scripts/check_loop_memory_state.py' --fail-under=90
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
python3 scripts/check_loop_memory_state.py
python3 scripts/check_loop_memory_state.py --state-root <rebuilt-schema-v2-state>
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format markdown
git diff --check
```

## Required Reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human Review Focus

- Cross-initiative next pointers fail before merge and during generated-state
  validation.
- Schema v1 has no executable acceptance path.
- A same-initiative successor must exist at the reviewed head and its contract
  heading must match the merge-intent ID and title.
- A hostile or stale signed state rebuild cannot bypass protected-main
  freshness or signature checks.
- Global priority remains human-owned and is not inferred from the last merge.
- No product runtime or existing engineering gate is weakened.

## Stop Conditions

- Rebuild requires editing historical authority or generated state by hand.
- Any proposed implementation path would accept schema-v1 input.
- The workflow would execute pull-request-head code with write credentials.
- The change requires a product runtime, dependency, or coverage-threshold
  modification.
- The same blocking defect remains after two repair cycles.

## Required Regression Tests

- schema-v2 same-initiative successor accepted;
- schema-v2 null successor accepted and rendered without a selected next chunk;
- schema-v2 cross-initiative, wrong-directory, non-canonical-heading,
  missing-contract, duplicate-contract, and title-mismatched successors
  rejected;
- every schema-v1 intent and generated-state form rejected;
- signed schema-v1 state rejected, fixed paths cleared, this chunk used as the
  unique schema-v2 bootstrap, re-signed, freshness-verified, and accepted by
  the independent checker;
- cross-initiative live-state and historical-ledger records rejected;
- stale dispatch target rejected with both valid and invalid existing state;
- queued push event reconciles only to current protected `main`;
- workflow step order, trusted checkout, freshness binding, fixed push target,
  and absence of bypass controls validated structurally;
- stale authored-main claims for PR #119, PR #120, and PR #122 rejected while
  inactive AUTH-06 and ART-02A1 planning remains valid.
