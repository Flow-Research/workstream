# Chunk Contract: WS-ENG-008-06 — Changed-Module Mutation Pilot

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Measure whether tests detect plausible faults in eligible changed pure-logic
modules without immediately imposing an uncalibrated global merge threshold.

## Why this chunk exists

Coverage proves execution but not assertion sensitivity. Workstream has no
mutation-testing engine or authenticated mutation evidence.

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

## Machine-checkable scope

```chunk-scope-json
{
  "schema_version": 1,
  "chunk_id": "WS-ENG-008-06",
  "phase": "implementation",
  "risk_class": "L1",
  "allowed_paths": [
    "backend/pyproject.toml",
    "backend/scripts/mutation_policy.py",
    "backend/tests/test_mutation_policy.py",
    ".github/workflows/backend.yml",
    "scripts/assurance-requirements.txt",
    "scripts/test_agent_gates.py",
    "docs/operations_backend_testing.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/STATUS.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-06-changed-module-mutation-pilot.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-internal-review-evidence.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-pr-trust-bundle.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-adversarial-proof.md",
    ".agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-external-review-response.md",
    ".agent-loop/merge-intents/WS-ENG-008-06.json"
  ],
  "forbidden_paths": ["backend/app/**", "backend/alembic/**"],
  "required_reviewers": ["senior engineering", "qa/test", "security/auth", "product/ops", "architecture", "ci integrity", "docs", "reuse/dedup", "test delta"],
  "verification_commands": ["mutation-policy-tests", "mutation-policy-lint", "agent-gate-tests", "markdown-links", "stale-wording", "git-diff-check"]
}
```

## Allowed files

```text
backend/pyproject.toml
backend/scripts/mutation_policy.py
backend/tests/test_mutation_policy.py
.github/workflows/backend.yml
scripts/assurance-requirements.txt
scripts/test_agent_gates.py
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/STATUS.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/chunks/WS-ENG-008-06-changed-module-mutation-pilot.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-internal-review-evidence.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-pr-trust-bundle.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-adversarial-proof.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/reviews/WS-ENG-008-06-external-review-response.md
.agent-loop/merge-intents/WS-ENG-008-06.json
```

## Not allowed

```text
application behavior or production dependency changes
global or blocking mutation percentage
replacement, reduction, or bypass of coverage, semantic lanes, API E2E, or full-suite aggregation
mutation of migrations, generated code, schemas/declarations, adapters, or unowned modules without explicit eligibility
use of stale QUALITY branches as implementation authority
unbounded runtime, silent timeout exclusion, or “one mutant killed” success rule
```

## Acceptance criteria

- [ ] Discovery reconciles current Backend workflow and records which dormant
      QUALITY ideas, if any, are recreated rather than cherry-picked as authority.
- [ ] One mutation engine and its complete transitive closure are exactly pinned
      and hash-locked in `scripts/assurance-requirements.txt`, installed with
      `--require-hashes`, and run only on eligible changed pure-logic modules.
- [ ] Authenticated evidence reports eligible, generated, killed, survived,
      timeout, suspicious, excluded, and error counts plus module/test identity.
- [ ] Every survivor and non-killed category requires explicit classification;
      missing or malformed evidence fails the pilot job.
- [ ] Pilot is non-blocking only with respect to score; infrastructure errors,
      malformed evidence, scope escape, or weakened coverage remain blocking.
- [ ] Existing full suite, API E2E, exact-custody semantic lanes, 78 percent
      global floor, and protected 90 percent floors remain exact and authoritative.
- [ ] Mutation execution has a hard 12-minute command limit inside a 15-minute
      job limit, records exact-head elapsed time, and runs independently so it
      adds no more than two minutes to the existing required Backend critical
      path. A later blocking threshold requires a separate reviewed plan and
      explicit human decision.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-008-07` and requires a
      separate explicit start.

## Verification commands

```bash
cd backend
python -m pytest -q tests/test_mutation_policy.py
ruff check scripts/mutation_policy.py tests/test_mutation_policy.py
cd ..
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

- Is the pilot genuinely bounded and non-gamable?
- Are coverage and full-suite gates unchanged?
- Is all dormant QUALITY work treated only as discovery input?

## Stop conditions

Stop if the engine cannot be pinned, hosted runtime is unbounded, evidence is
not complete, or any existing required test/coverage lane must weaken.
