# Internal Review Evidence: Week 1 And Week 2 Deterministic Hardening

Date: 2026-06-13

## Scope

This review covers the deterministic Week 1 and Week 2 hardening pass:

- Week 1 real API drill
- Week 2 real API drill
- guide activation checker-name validation
- revision policy state validation
- checker result and audit invariant checks
- local Postgres test database guard
- backend CI database alignment with the E2E guard
- checker-policy documentation cleanup

## Reviewer Tracks

### Senior Engineering

Result: valid findings addressed. Final bounded re-review reported no blocking findings.

Findings:

- current docs still advertised unregistered checker names as policy checkers
- checker policy docs contained duplicate/conflicting checker entries
- the roadmap listed `check_policy_context_present` twice in the first checker set

Resolution:

- removed unregistered checker names from current policy-facing docs/templates
- documented readiness, lifecycle movement, revision closure, and pre-review routing as lifecycle guards unless a checker is registered
- removed duplicate checker template rows and duplicate roadmap checker entries
- added guide activation validation that rejects unregistered required or warning checker names

### QA/Test

Result: valid findings addressed. Final bounded re-review reported no blocking findings.

Findings:

- checker result assertions used sets and could miss duplicate persisted checker results
- Week 2 audit invariant could match event type and trigger source on different audit rows

Resolution:

- Week 1 and Week 2 drills now fail on duplicate checker result names
- Week 2 DB invariants now bind expected audit event type, `checker_run_id`, and `trigger_source` on the same audit event row
- real API drills were rerun against local `workstream_test` Postgres

### Security/Auth

Result: valid findings addressed. Final bounded re-review reported no blocking findings.

Findings:

- the E2E database guard allowed plain local `workstream`, which could be a tunnel/proxy to a shared database

Resolution:

- destructive real API drills now allow only local async Postgres databases named `workstream_test` or `test_workstream` by default
- plain `workstream` requires the explicit `WORKSTREAM_ALLOW_NONLOCAL_E2E_DATABASE=I_UNDERSTAND_THIS_WRITES_DATA` override for E2E drills
- Docker Compose now creates `workstream_test` on fresh local Postgres volumes
- Flow token negative probes, role visibility, worker redaction, and checker policy activation hardening remain covered by real API drills and tests

CI follow-up:

- backend CI initially still pointed the Week 1 real API drill at `/workstream`
- the hardened E2E guard correctly refused that non-test database name
- backend CI now creates, health-checks, and uses `/workstream_test`
- QA/test and security/auth CI-fix reviewer passes reported no blocking findings

### Product/Ops

Result: valid findings addressed. Final bounded re-review reported no blocking findings.

Findings:

- checker template duplicated `check_forbidden_files`, `check_confidentiality_attestation`, and `check_low_quality_generated_artifacts`
- checker framework duplicated `check_submission_packet`
- proposal source still referenced a stale guide-attached checker
- roadmap status undercounted the expanded Chunk 10 trial matrix
- template checker policy and project guide checker lists diverged
- Day 10 docs still referenced five sample submissions
- public lifecycle wording used uppercase outcome-state names where canonical public decision language was required

Resolution:

- checker templates now show only the registered v0.1 checker names
- status now describes the expanded real API sample matrix
- retired checker names were removed from current policy-facing docs
- DB URL wording now separates normal local development from destructive real API drills
- project guide and checker policy templates now share the same registered checker set
- Day 10 docs now use expanded sample matrix wording
- public lifecycle prose now uses `accept`, `needs_revision`, `reject`, or accepted/rejected work wording as appropriate
- proposal source checker list now matches the locked nine-checker set and no longer carries checker version suffixes

## Sub-Agent Sessions

The first reviewer pass completed for all required tracks and produced the findings above.

Later broad follow-up reviewer sessions became stale after repeated waits. Root-cause checks showed the sub-agent service and repo access were healthy; the broad diff-review prompts were too large. The final required reviewer tracks were rerun one at a time with bounded file scopes on `gpt-5.5` high reasoning. QA/test, security/auth, product/ops, and senior engineering completed and reported no blocking findings after fixes. Product/ops was rerun again after the proposal checker-list cleanup and reported no blocking findings. QA/test and security/auth were also rerun on the backend CI database fix and reported no blocking findings.

Open sub-agent sessions: none.

## Validation

Passed:

```bash
cd backend && .venv/bin/python -m ruff check app tests scripts
```

Result: `All checks passed!`

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week1_api_e2e.py
```

Result: `Week 1 real API e2e passed` and `PASS Week 1 database invariants`.

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py
```

Result: `Week 2 real API e2e passed` and `PASS Week 2 database invariants`.

Passed:

```bash
cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python -m pytest -q
```

Result: `114 passed in 1128.04s`.

Passed:

```bash
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
```

Result: `100.0%`.

Passed:

- stale wording scan
- retired checker-name scan for current policy-facing docs
- Markdown relative link check
- `git diff --check`
- XLSX/sheets check: no local sheet exports present

## Closure

Valid findings addressed.

Open sub-agent sessions: none.
