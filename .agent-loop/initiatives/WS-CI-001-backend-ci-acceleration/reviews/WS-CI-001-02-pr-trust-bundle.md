# PR Trust Bundle

## Chunk

`WS-CI-001-02` — Safe Routing, Cache, and Timing Refinement

Merge intent: `.agent-loop/merge-intents/WS-CI-001-02.json`

## Goal

Turn measured CI evidence and contributor PR #180 into prospective, bounded
implementation contracts without retroactively authorizing its code.

## Human-approved intent

The user directed the orchestrator to preserve strict zero-trust loop
engineering, review PR #180, and make the contributor work adoptable through
the normal plan, chunk, evidence, and PR process.

## What changed

- Recorded PR #180 measurements and review gaps as discovery.
- Decided not to implement routing, caching, sampling, or durable timing now.
- Defined reset-safety chunk 02A as the only declared successor.
- Defined later exact-custody semantic-lane chunk 02B after 02A evidence.
- Reserved routing/cache/timing reassessment for future planning chunk 03.

## Why it changed

PR #180 demonstrates a promising migrate-once direction, but its original diff
crosses destructive database reset and workflow-topology boundaries and lacked
prospective signed scope and complete exact-execution evidence.

## Design chosen

First prove runner-owned destructive reset containment under the existing CI
topology. Then, under a separate signed chunk, change to dependency-based lanes
with independent node, coverage, PostgreSQL, and MinIO custody.

## Alternatives rejected

- Merging PR #180 as-is was rejected because chat and retrospective artifacts
  cannot authorize implementation.
- One large reset-plus-workflow chunk was rejected as unreviewable L1/P0 scope.
- More arbitrary infrastructure shards were rejected because they add cost and
  do not address repeated migrations.
- Routing or sampling was rejected because it could suppress required proof.

## Scope control

Only WS-CI-001 planning, decision, risk, status, chunk-contract, review, and one
merge-intent file change. No workflow, backend, test, dependency, coverage, or
product runtime file changes.

## Product behavior

- [x] No Workstream product behavior changed.

## Acceptance criteria proof

- [x] Original routing/cache/timing options received an evidence-backed decision.
- [x] 02A and 02B have exact prospective file scope and immutable source commits.
- [x] Reset ownership, node custody, service isolation, coverage, and timing are explicit.
- [x] Only same-initiative 02A is declared and still requires a signed start.

## Tests/checks run

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_artifact_contracts.py
git diff --check origin/main...HEAD
```

All passed; 95 Agent Gate tests passed.

## Test delta

No executable tests changed. Future contracts prohibit removed, skipped,
deselected, or weakened tests and require exact collection/completion proof.

## CI integrity

- [x] No workflow or package script changed
- [x] Full suite remains required
- [x] Global 78% and all protected 90% floors remain blocking
- [x] No cache, routing, sampling, or timing authority introduced

## Reviewer results

Reviewed code SHA: c10f084a712660db413cd286340d7dede05c8ead

Reviewed at: 2026-07-22T11:12:00Z

Reviewer run IDs: eng006_senior_arch_docs, eng006_qa_ci_tests, eng006_security_ops_reuse

All nine required tracks passed after the documented repairs, with no remaining
condition or blocker.

## External review

PR #180 supplied discovery and contributor measurements. Its review findings
were incorporated into prospective contracts; it remains unauthorized for
merge under this planning chunk. CodeRabbit's three valid scope/wording findings
were repaired. Its title-change suggestion was rejected because the trust bundle
and merge intent intentionally match the canonical signed chunk title; the goal
and PR title describe the planning amendment and reset-safety successor.

## Remaining risks

02A must prove destructive reset safety, and 02B must prove hosted exact-node,
coverage, isolation, and timing custody. Neither implementation is authorized
by this PR alone.

## Follow-up work

After this PR merges and automation reconciles it, dispatch a signed start for
02A only. Do not start 02B or 03 automatically.

## Human review focus

- Prospective authorization rather than retroactive adoption.
- 02A/02B boundary and exact file scope.
- Destructive reset containment and independent node custody.
- Preservation of Konan's authorship.

## Human merge ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
