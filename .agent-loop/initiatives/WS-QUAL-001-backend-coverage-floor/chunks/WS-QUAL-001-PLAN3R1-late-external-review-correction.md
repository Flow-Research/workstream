# Chunk Contract: WS-QUAL-001-PLAN3R1 — Late External Review Correction

## Parent initiative

`WS-QUAL-001` — Behavior And Mutation Assurance

## Goal

Correct the five valid CodeRabbit findings that arrived before PR #272 merged
but were not addressed before the branch was deleted.

## Why this chunk exists

PR #272 changed planning only, so no unsafe mutation runtime was deployed.
However, its merged plan leaves ambiguity in dependency custody, mutation
outcome handling, fixture-only classifications, target selection, and exact
Backend evidence binding. Those ambiguities must be removed before `04M` may
start.

## Risk class

L1 — CI/test policy planning correction.

## Machine scope

```chunk-scope-json
{
  "schema_version": 1,
  "chunk_id": "WS-QUAL-001-PLAN3R1",
  "allowed_paths": [
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/CHUNK_MAP.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/PLAN.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/STATUS.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/README.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/WS-QUAL-001-04M-changed-scope-mutation-pilot.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/WS-QUAL-001-05M-blocking-behavior-mutation-gate.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/chunks/WS-QUAL-001-PLAN3R1-late-external-review-correction.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/reviews/WS-QUAL-001-PLAN3-pr-trust-bundle.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/reviews/WS-QUAL-001-PLAN3R1-external-review-response.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/reviews/WS-QUAL-001-PLAN3R1-internal-review-evidence.md",
    ".agent-loop/initiatives/WS-QUAL-001-backend-coverage-floor/reviews/WS-QUAL-001-PLAN3R1-pr-trust-bundle.md",
    ".agent-loop/merge-intents/WS-QUAL-001-PLAN3R1.json"
  ],
  "forbidden_paths": [
    ".github/**",
    "backend/**",
    "scripts/**"
  ],
  "verification_commands": [
    "markdown-links",
    "stale-wording",
    "lightweight-agent-gates",
    "git-diff-check"
  ]
}
```

## Not allowed

```text
workflow, dependency, backend, test, or mutation implementation
coverage-threshold changes
automatic start of 04M or 05M
changes outside the WS-QUAL-001 correction evidence and merge intent
```

## Acceptance criteria

- [ ] PR code cannot choose or modify the mutation-tool dependency authority.
- [ ] Eligible changed production targets are always selected; bounded
      test-only behavior claims are additive and name owning test nodes.
- [ ] Every engine outcome fails closed or has an independently verified typed
      policy classification.
- [ ] Fixture-only changes require proof before receiving a non-behavioral
      classification.
- [ ] PLAN3 Backend evidence names both exact run and commit.
- [ ] All five late comments are recorded and resolved before `04M` starts.

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- CI integrity
- docs
- reuse/dedup
- test delta

## Human review focus

Confirm this correction closes the five late comments without implementing or
pre-authorizing mutation CI.

## Stop conditions

Stop if the correction requires executable workflow, dependency, backend, test,
or mutation changes.
