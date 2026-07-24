# Chunk Contract: WS-ENG-008-04 — Loop-Memory Property Invariants

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Use bounded, reproducible property-based tests to explore signed loop-memory
invariants beyond hand-selected examples.

## Why this chunk exists

The reducer and validators have strong example/mutation coverage, but generated
event sequences can expose state interactions not anticipated in fixtures.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/CHUNK_MAP.md`

## Risk class

L1

## SLA

P2

## Start phase

`implementation`

## Allowed files

```text
scripts/agent-gate-requirements.txt
scripts/test_loop_memory_properties.py
scripts/test_agent_gates.py
.github/workflows/agent-gates.yml
docs/operations_post_merge_memory.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/**
.agent-loop/merge-intents/WS-ENG-008-04.json
```

## Not allowed

```text
loop-memory reducer, signer, schema, authority, workflow write behavior, or recovery changes
auth/application/product behavior
unbounded examples, nondeterministic network/time dependence, or hidden flaky retry
coverage, test, review, or human gate weakening
```

## Acceptance criteria

- [ ] Hypothesis is exactly pinned with reproducible dependency evidence.
- [ ] A bounded CI profile and a documented deeper local profile have explicit
      examples, deadlines, health checks, and failure reproduction instructions.
- [ ] Generated event sequences prove at most one active chunk per initiative,
      concurrent independence, completed identity non-restart, cross-initiative
      denial, stale-main/tip denial, idempotent replay, and projection/ledger
      agreement.
- [ ] Invalid paths, phases, identities, permissions, blob bindings, collisions,
      and malformed scalar types fail closed without partial state mutation.
- [ ] Properties reuse real reducers/validators and compare independent
      invariants; they do not reimplement expected behavior identically.
- [ ] Hosted runtime is measured and remains inside the chunk's approved budget.
- [ ] Existing deterministic regression and coverage suites remain unchanged.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-008-05` and requires a
      separate explicit start.

## Verification commands

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p hypothesis.extra.pytestplugin -q scripts/test_loop_memory_properties.py
python3 scripts/test_agent_gates.py
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

- Are the properties independent, bounded, deterministic, and security-relevant?
- Can every failing case be reproduced from evidence?
- Did the chunk avoid changing the behavior it tests?

## Stop conditions

Stop if Hypothesis introduces flaky required CI, cannot be reproducibly pinned,
or exposes a production behavior fix outside this test-only contract.

