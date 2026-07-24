# Chunk Contract: WS-ENG-008-05 — Authorization Property Invariants

## Parent initiative

`WS-ENG-008` — Repository-Native SDLC Assurance

## Goal

Add bounded property tests for deny-default authorization, action custody,
resource scope, lifecycle state, and grant invariants after active AUTH work is canonical.

## Why this chunk exists

Authorization has extensive examples, but generated combinations can prove
closed behavior across unknown actions, actors, scopes, and lifecycle states.

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
backend/pyproject.toml
backend/tests/test_authorization_properties.py
.github/workflows/backend.yml
scripts/assurance-requirements.txt
docs/operations_authorization_service.md
.agent-loop/initiatives/WS-ENG-008-repository-native-sdlc-assurance/**
.agent-loop/merge-intents/WS-ENG-008-05.json
```

## Not allowed

```text
authorization application code, catalogue, kernel, schemas, routes, grants, audit, migration, or activation changes
changes before AUTH-10C and any intervening AUTH work are merged/stopped and rediscovered
database/network dependence for pure properties
coverage, test, auth-denial, review, or human gate weakening
```

## Acceptance criteria

- [ ] Start evidence is based on main containing the canonical outcome of
      AUTH-10C and discovery records exact current action/catalogue ownership.
- [ ] Backend installs the exact hash-locked Hypothesis closure from
      `scripts/assurance-requirements.txt` with `--require-hashes` and reuses the
      bounded profiles established by `WS-ENG-008-04` without a second path.
- [ ] Generated unknown actions/resources/actors deny by default with bounded
      non-sensitive errors and no grant/evidence mutation.
- [ ] Project/resource scope cannot cross tenants or projects; revoked,
      expired, future, wrong-kind, and lifecycle-ineligible grants never allow.
- [ ] Planned actions remain unreachable until their owning activation chunk;
      custody transfer alone cannot enable them.
- [ ] Authorized combinations preserve exact action/resource/actor lineage and
      do not imply unrelated permissions.
- [ ] Tests exercise public kernel/service contracts without copying the
      implementation's decision expression into the oracle.
- [ ] The focused hosted authorization property command has a hard 120-second
      limit and records exact-head elapsed time; timeout is failure.
- [ ] Exactly one schema-v2 merge intent names `WS-ENG-008-06` and requires a
      separate explicit start.

## Verification commands

```bash
cd backend
python -m pytest -q tests/test_authorization_properties.py
ruff check tests/test_authorization_properties.py
cd ..
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

- Are the properties aligned with the post-AUTH-10C canonical contract?
- Do the oracles remain independent of the implementation?
- Does any test accidentally activate or redefine an AUTH action?

## Stop conditions

Stop if AUTH remains active/unmerged, tests require production-code changes, or
the property oracle cannot be independent.
