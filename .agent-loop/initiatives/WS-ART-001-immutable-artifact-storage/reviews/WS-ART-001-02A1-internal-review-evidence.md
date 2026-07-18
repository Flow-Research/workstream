# Internal Review Evidence: WS-ART-001-02A1

## Chunk

`WS-ART-001-02A1`: External Service Adapter Foundation

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 05d667ae1f4afe0f4cac2050dbe340213437a0bd

Reviewed at: 2026-07-15T12:27:26Z

Reviewer run IDs: senior-engineering=019f65b3-8c17-79f0-a413-38cd63539972; QA/test=019f65b3-9bd5-7af1-a854-da77fd6454b9; security/auth=019f65b3-abb0-7ea3-9f45-53dc67f4f6f9; product/ops=019f65b8-a180-7831-82ea-eedbc50fb123; architecture=019f65b3-915d-73f1-a4f7-1ed2b2a2d914; CI-integrity=019f65b8-a80c-7822-bf73-7fcd80138b8a; docs=019f65c9-a6c1-7b12-b676-47af7fbe270a; reuse/dedup=019f65b8-a445-7f81-9ede-101b8d45a752; test-delta=019f65b8-af50-7b70-9f18-407ca4ed2110

Foundation review run IDs: senior-engineering=019f6527-72b0-7d83-979c-4eb6fdfdef96; QA/test=019f6527-82f9-7573-840b-930241a75e17; security/auth=019f6527-9372-7712-8935-ed9376fd95a0; product/ops=019f652c-6005-7881-8ec4-02489108199f; architecture=019f6527-78db-7a80-a285-1242f2be429b; CI-integrity=019f652c-7643-7163-9b2b-26cbc0cdf876; docs=019f6531-f86a-7b00-8750-a52a15e5eb2e; reuse/dedup=019f652c-6b85-78d2-bf89-331044d96dbd; test-delta=019f652c-8338-7170-88cc-7160a62e2636

Repair review run IDs: cycle-one senior-engineering=019f6511-ed30-7a72-92e4-ce59e36ddb66, architecture=019f6511-fde3-7081-b2cd-2e145d981fe9, QA/test=019f6512-0f8c-7d32-a183-7cd8de839b83, security/auth=019f6512-4320-77e2-bf6b-7d4026c4f8dd; cycle-two senior-engineering=019f6520-0f44-7e13-b582-d97cfb71a512, architecture=019f6520-1e8b-7c93-8d46-052e760f4d30, QA/test=019f6520-2fe1-7f61-bd32-11f462f7a83c, security/auth=019f6520-4dc6-7902-adc4-0b6c713b7124

After the reviewed SHA, only initiative review evidence and status files change.

## Reviewed Change

- Added immutable canonical capability/provider identity and shared stable
  configuration, availability, and protocol error categories.
- Added an instance-local typed factory with explicit composition-root
  registration, duplicate and unknown provider rejection, exact identity
  verification, and secret-safe construction-error remapping.
- Added focused coverage for malformed keys, identity drift and equality
  bypasses, secret-bearing subclasses, constructor and identity failures,
  exception chains, and every shared root-error category.
- Added the exact scoped 90 percent CI coverage command while preserving the
  earlier artifact gate and repository-wide 78 percent floor.
- Did not migrate ArtifactStore, auth, project agents, or any other capability.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Foundation is small, explicit, centralized, and operationally bounded. |
| QA/test | PASS | None | Acceptance criteria and adversarial identity/error paths are covered. |
| security/auth | PASS | None | Canonical identity and provider-exception data cannot escape the factory boundary. |
| product/ops | PASS | None | No product lifecycle, operator, contributor, reviewer, payment, or reputation behavior changed. |
| architecture | PASS | None | ADR 0014 boundary is preserved without capability migration or service-location behavior. |
| CI integrity | PASS WITH LOW RISKS | None | Scoped 90 percent and existing cumulative coverage gates remain fail closed. |
| docs | PASS | None | ADR, chunk, queue, status, successor, and merge intent remain consistent. |
| reuse/dedup | PASS | None | No existing shared factory was duplicated and capability-specific entry points remain untouched. |
| test delta | PASS WITH LOW RISKS | None | Tests are additive, adversarial, and do not weaken existing assertions or exclusions. |

## Valid Findings Addressed

- Constructor and `identity` property exceptions could retain provider secrets.
  The factory now maps unexpected failures to fresh bounded configuration
  errors outside the provider exception context.
- The branch lagged merged AUTH-06 during review. It was rebased onto
  `f599551`, and the final diff contains no authorization rollback.
- Root errors accepted arbitrary runtime identity objects. They now retain only
  an exact `ExternalServiceAdapterIdentity` or `None`.
- Identity subclasses could carry extra state and adapter-controlled equality
  could certify a noncanonical identity. The boundary now requires the exact
  canonical type before equality.
- Constructor-raised shared errors could preserve an earlier transport error
  through `__context__`. The factory remaps each category to a fresh known root
  error and raises it without a provider cause or context.
- CodeRabbit noted that the unexpected-constructor branch relied on CPython
  clearing the handled exception before the later raise. The branch now uses
  explicit `from None`, matching the sibling sanitized-error path. Eight
  technical and operational reviewer tracks passed the exact one-line code
  delta; the docs track passed the completed evidence provenance separately.

## Commands Run

```bash
cd backend && .venv/bin/ruff check app tests scripts
cd backend && .venv/bin/docstr-coverage --config .docstr.yaml
cd backend && .venv/bin/python -m pytest -q \
  tests/test_external_service_adapters.py \
  --cov=app.interfaces.external_services \
  --cov-report=term-missing --cov-fail-under=90
python3 scripts/test_agent_gates.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/update_post_merge_memory.py validate-merge-intent \
  --base-ref origin/main
git diff --check
```

Results: Ruff passed; repository docstring coverage passed at 94.5 percent; 15
focused tests passed with 100 percent coverage of
`app/interfaces/external_services.py`; 71 agent-gate tests passed; stale
artifact, stale Workstream wording, Markdown link, merge-intent, and diff
checks passed.

The exact-head isolated PostgreSQL suite reached beyond 79 percent with no
reported failure before the user directed that the workstation run be stopped
because host contention makes repository-wide execution take multiple hours.
That interrupted run is not pass evidence. GitHub Backend CI owns the final
exact-head repository-wide suite and unchanged 78 percent coverage floor.

## Remaining Risks

- This chunk installs only the convention. No capability consumes it yet.
- GitHub Backend CI must pass the exact PR head before merge.
- `WS-ART-001-02A2` remains inactive until this PR merges and the user starts
  it explicitly.

## Stop Condition

Publish this chunk for external and human review, then stop. Do not start
`WS-ART-001-02A2` and do not merge without explicit user approval.
