# Chunk Contract: WS-QUAL-002-02 — Coverage-Context Candidate Evidence

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Emit non-authoritative callable-to-test candidates from exact local coverage contexts and measure cost without adding CI infrastructure.
## Why this chunk exists
Imports do not prove behavior ownership.
## Approved plan reference
- INTENT: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/CHUNK_MAP.md`
## Risk class
L1.
## SLA
P2.
## Allowed files
```text
backend/scripts/behavior_ownership.py
backend/scripts/run_test_lanes.py
backend/tests/test_behavior_ownership.py
backend/tests/test_ci_test_lanes.py
backend/pyproject.toml
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/STATUS.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/chunks/WS-QUAL-002-02-context-evidence.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/reviews/WS-QUAL-002-02-*
```
## Not allowed
```text
backend/app/**; .github/workflows/**; reviewed catalogue population; mutation reactivation; coverage or test weakening; any required-check or blocking-gate change
scripts/behavior-ownership.schema.json; .ci/behavior-ownership/**
```

## Local command and artifact boundary

The implementation adds one manual command:

```bash
cd backend
.venv/bin/python -m scripts.behavior_ownership context-evidence \
  --target backend/scripts/behavior_ownership.py \
  --test-module tests/test_behavior_ownership.py \
  --output /tmp/workstream-context-evidence.json
```

The command collects and executes the exact nodes in the named test module by
reusing the `scripts.run_test_lanes` pytest collection/completion plugin. It
runs coverage with per-test contexts, maps only executed callable lines to
completed exact node IDs, and writes one new regular output file exclusively.
The output path must not already exist.

The output uses a separate
`workstream.behavior-ownership-context-evidence.v1` envelope. It is temporary,
local, non-catalogue evidence: it is not committed under
`.ci/behavior-ownership/`, is not a catalogue `candidate` or `reviewed` record,
cannot be consumed by `validate_catalogue()`, and cannot establish ownership.
The artifact binds its exact head, target, callable spans, collected/completed
nodes, skip/deselect state, line-context mappings, elapsed time, and digest.
It contains no test output, environment values, credentials, request payloads,
logs, or database values.
## Acceptance criteria
- [ ] Context evidence binds exact head, callable lines, and collected nodes.
- [ ] Test discovery, collection, and completion evidence reuse `run_test_lanes.py` rather than introducing a parallel collector.
- [ ] Candidate output cannot satisfy reviewed ownership.
- [ ] Context evidence is a separate uncommitted local artifact and cannot be
      parsed as a catalogue record or consumed by catalogue validation.
- [ ] The prototype is a local/manual command only and adds no workflow or required check.
- [ ] Added local runtime is at most two minutes and each generated artifact is at most 10 MiB; exceeding either limit stops adoption and triggers redesign.
- [ ] Artifacts contain only commit SHAs, lane identity, collection/completion status, skip/deselect status, target paths, callable spans, collected node IDs, line-coverage metadata, and an artifact digest or immutable canonical-lane manifest reference; they never contain environment values, secrets, tokens, request payloads, logs, or database values.
- [ ] Validation rejects stale-head, partial, incomplete, skipped, deselected, digest-mismatched, or overwritten evidence as candidate input.
## Verification commands
```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_behavior_ownership.py tests/test_ci_test_lanes.py)
(cd backend && tmp_dir=$(mktemp -d) && trap 'rm -rf "$tmp_dir"' EXIT && \
  .venv/bin/python -m scripts.behavior_ownership context-evidence \
    --target backend/scripts/behavior_ownership.py \
    --test-module tests/test_behavior_ownership.py \
    --output "$tmp_dir/context-evidence.json" && \
  .venv/bin/python -m scripts.behavior_ownership validate-context-evidence \
    --input "$tmp_dir/context-evidence.json")
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, QA, security, CI integrity, reuse/dedup, and test delta.
## Human review focus
Candidate-only custody, no added CI infrastructure, and local cost.
## Stop conditions
Stop if contexts destabilize Backend or require PR-controlled authority.
