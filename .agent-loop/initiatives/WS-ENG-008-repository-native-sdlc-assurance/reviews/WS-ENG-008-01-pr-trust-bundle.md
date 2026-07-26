# PR Trust Bundle: WS-ENG-008-01

## Chunk

`WS-ENG-008-01` — Machine-Checkable Chunk Scope

Merge intent: `.agent-loop/merge-intents/WS-ENG-008-01.json`

## Goal

Make every post-cutover implementation/specification PR prove its complete Git
delta against the exact machine-readable contract selected by signed start.

## Human-approved intent

The approved contract is
`.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-01-machine-checkable-chunk-scope.md`.

## Signed Start Provenance

- Signed start run: `30191914510`
- Authorized main SHA: `bd2203d5e8a972d8afbf833805b92ed70dedee4a`
- Phase: `implementation`
- Contract path: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-01-machine-checkable-chunk-scope.md`
- Signed contract blob SHA: `2fb0afba71653e7aefcc074079fe98f44051c068`
- Reviewed implementation SHA: `1ef5c3bd0bffedec684ae8b6cec2e6affbcb3b21`

## What changed

- Added strict schema-v1 contract parsing and closed path/command/reviewer registries.
- Added authenticated signed-ledger start selection and exact contract-blob custody.
- Added byte-safe complete Git delta, mode, Unicode, and collision enforcement.
- Added trusted-base Agent Gates execution with one bounded cutover bootstrap.
- Upgraded ENG-008 contracts 02–07 before naming chunk 02.
- Updated contributor, architecture, glossary, policy, and contract-template guidance.

## Design chosen

The signed ledger selects authority; the immutable start blob supplies machine
scope. Agent Gates authenticate generated state, reduce initiative-local events,
compare all base/head/index/worktree paths, and execute only repository-owned
command mappings. After cutover the interpreter and validators come from the
trusted base rather than candidate code. Work already active at cutover may
finish only under its exact signed legacy Allowed-files fence.

## Scope control

All 22 implementation files are explicitly listed by the signed human contract
and the new bootstrap machine block. No product, API, database, migration,
authorization, payment, signing, start/cancel, branch-protection, secret,
dependency, or coverage behavior changed.

## Acceptance criteria proof

- Strict schema and human agreement: parser mutations plus all seven ENG-008 contracts pass.
- Closed path grammar and complete Git delta: 27 focused unit/integration tests pass.
- Signed cutover/grandfather custody: authenticated ledger fixtures and exact live state pass.
- Reviewer/command binding: internal evidence gate regression passes.
- Trusted Agent Gate integration: 102 regression tests pass.
- Successor control: one schema-v2 intent names `WS-ENG-008-02` with explicit start required.

## Tests/checks run

```bash
python3 scripts/check_chunk_contract.py --base-ref origin/main --head-ref HEAD --state-ref origin/automation/loop-memory
python3 scripts/test_check_chunk_contract.py
python3 scripts/test_agent_gates.py
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
ruff check scripts/check_chunk_contract.py scripts/check_internal_review_evidence.py scripts/test_check_chunk_contract.py scripts/test_agent_gates.py
git diff --check origin/main...HEAD
```

Result: all passed on the reviewed implementation plus evidence-only publication.

## Test delta

- Added 27 focused schema, signed-state, path, Git-mode, collision, and workflow tests.
- Added Agent Gate regressions for trusted execution and evidence binding.
- No test was removed, skipped, deselected, or weakened.

## CI integrity

- Coverage thresholds and existing 90-percent loop-memory coverage jobs are unchanged.
- No `continue-on-error`, path exclusion, unpinned action, permission expansion,
  credential persistence, package-script bypass, or test weakening was added.

## Reviewer results

Reviewed code SHA: `1ef5c3bd0bffedec684ae8b6cec2e6affbcb3b21`

Reviewed at: `2026-07-26T07:48:30Z`

Reviewer run IDs: `ci02b_lane_runner`, `ci02b_cr_arch`, `ci02b_cr_ci`, `ci02b_cr_docs`, `ci02b_cr_reuse`, `ci02b_cr_test_delta`

All nine required tracks passed. Architecture and reuse recorded only Low-risk
future consolidation opportunities; there are no blocking findings.

## Remaining risks

Some validated-ledger, merge-intent, and reviewer-name parsing remains locally
duplicated. Consolidating authority-sensitive helpers requires its own reviewed
contract and must not delay this closed enforcement cutover.

## Human review focus

- Trusted-base versus one-time bootstrap execution in `agent-gates.yml`.
- Signed-ledger and exact-blob selection, including grandfather reduction.
- NUL/Unicode/mode/collision handling in `check_chunk_contract.py`.
- Exact schema blocks for successors 02–07.

## External review

- CodeRabbit: pending
- GitHub checks: pending

## Human ownership

The PR remains stopped for explicit review and merge approval. Its merge will
not start `WS-ENG-008-02`.

