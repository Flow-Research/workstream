# Internal Review Evidence: WS-AUTH-001-01

## Chunk

`WS-AUTH-001-01` - Adopt Authorization Baseline And Repository Contracts

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 3815bbd2ade4ada7f03be611282d38e93dba1b7e

Reviewed at: 2026-07-11T20:03:18Z

Reviewer run IDs: senior-engineering=/root/auth01_plan_engineering; QA/test=/root/auth01_plan_quality_ci; security/auth=/root/auth01_plan_security_product; product/ops=/root/auth01_plan_security_product; architecture=/root/auth01_plan_engineering; docs=/root/auth01_plan_security_product; CI-integrity=/root/auth01_plan_quality_ci; reuse/dedup=/root/auth01_plan_engineering; test-delta=/root/auth01_plan_quality_ci

## Reviewed Change

Implementation freeze SHA: `be0b836` includes the CI terminology assertion
repair. Final reviewed SHA `3815bbd` adds only reviewed scope-count and
latest-main lifecycle-memory reconciliation around that unchanged
implementation.

- Adopted ADR 0012 and the canonical authorization specification/runbook.
- Preserved external Flow authentication ownership while assigning local
  actors, grants, permissions, guards, idempotency, invalidation, and evidence
  to Workstream modules.
- Standardized five administrative grants, three exact-project contributor
  grants, `/api/v1`, system-only Operator scope, and registered recovery
  permissions.
- Reconciled active architecture, operations, product-flow, template, diagram,
  roadmap, and durable-memory documents.
- Added an active-document scanner, direct fail-closed Agent Gates invocation,
  independent regression fixtures, and a pinned local diagram renderer.
- Reserved worker terminology for qualified Celery/checker/setup/system
  processes; human actors and human-facing prompt wording use Contributor.
- Merged latest `main` through PR #90, preserved its correction provenance and
  activation guards, and moved the planned auth migration sequence after its
  new `0015` migration.
- Merged the PR #94 post-merge memory update from latest `main` and reconciled
  the active authorization gate without reactivating `WS-POL-002-04`.
- Kept all eight imported reference inputs and their checksum/manifest records
  byte-immutable.
- Incorporated PR #90 correction and activation semantics without importing or
  claiming its backend implementation.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS | None | Latest-main merge, scanner action families, migration sequence, scope, and trust state are coherent. |
| QA/test | PASS | None | 31 independent gate tests and 234 project tests pass; no tests were weakened. |
| security/auth | PASS | None | Internal workers remain fixed technical principals; human grants and actions fail the terminology gate. |
| product/ops | PASS | None | Contributor vocabulary, PR #90 correction behavior, activation, and chunk gating remain correct. |
| architecture | PASS | None | Auth migrations now follow main `0015` linearly through `0023`; no authored runtime-logic drift exists. |
| docs | PASS | None | Canonical corpus, PR #90 merge state, diagrams, runbook, and lifecycle memory are consistent. |
| CI integrity | PASS | None | Scanner invocation is direct and fail closed; no workflow step or threshold was weakened. |
| reuse/dedup | PASS WITH LOW RISKS | None | Existing gate, discovery, rendering, and test conventions are reused without a new framework. |
| test delta | PASS | None | Existing tests remain; independent fixtures cover worker vocabulary, identifiers, paths, and human-authority action families. |

## Valid Findings Addressed

- Restored source-compatible system-only Operator scope and
  `actor.profile.read_any`.
- Explicitly approved the eight changed diagram source/generated paths.
- Reconciled durable memory so PR #90 owns chunk 03 and chunk 04 remains
  inactive.
- Replaced a whole-file archive-marker exclusion with one exact line/rule
  exemption.
- Replaced self-derived scanner examples with independent fixtures.
- Expanded ordinary token-role, named-role-token, typed-profile, and generic
  admin authority detection.
- Removed attempted natural-language negation interpretation after adversarial
  review proved it ambiguous. Authority-shaped token/profile statements now
  fail closed regardless of negation; canonical docs state local-grant
  authority directly.
- Added a renderer that pins PlantUML 1.2026.6 by SHA-256, strips PNG metadata,
  fixes the source epoch/PDF identifier, and writes only approved artifacts.
- Replaced human `worker` terminology throughout the active corpus and the
  project-policy derivation prompt while preserving technical worker wording.
- Made technical-worker exemptions match-local and rejected human task, grant,
  review-decision, acceptance/rejection, and revision actions.
- Added explicit assignment/submission/checker terminology migration ownership
  and renumbered the auth sequence to `0016`-`0023` after merged-main `0015`.
- Addressed all valid CodeRabbit comments; retained user-approved `both` with
  explicit guarded union semantics instead of renaming it.
- Corrected the one stale agent-runtime prompt assertion reported by GitHub CI;
  the focused runtime tests pass and the assertion remains equally strict.

## Commands Run

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/test_agent_gates.py
python3 scripts/check_loop_memory_state.py
python3 -m py_compile scripts/check_stale_authorization_docs.py scripts/test_agent_gates.py
bash -n scripts/render_authorization_docs.sh
sha256sum -c docs/reference_specs/SHA256SUMS
PLANTUML_JAR=/tmp/workstream-plantuml.jar scripts/render_authorization_docs.sh
(cd backend && /home/abiorh/flow/workstream/backend/.venv/bin/python -m ruff check app/adapters/project_agents/openai_agent_sdk.py tests/test_projects.py)
(cd backend && /home/abiorh/flow/workstream/backend/.venv/bin/python -m pytest -q tests/test_projects.py)
(cd backend && /home/abiorh/flow/workstream/backend/.venv/bin/python -m pytest -q tests/test_agent_runtime.py)
git diff --check
```

Results: all passed. `test_projects.py` completed with 234 passing tests in
3576.81 seconds; the focused agent-runtime file completed with 2 passing tests.
Markdown links passed for 68 changed Markdown files. The pre-fix GitHub run
reported 463 passes plus the one stale terminology assertion; rerun remains an
external post-push check.

## Evidence Gate

Evidence gate: PASS

Scope exception: 85 changed paths and more than 500 changed lines are accepted because
this is one approved atomic active-document reconciliation plus its scanner,
tests, CI step, generated companions, latest-main merge, and two exact
terminology-only backend files. Splitting would leave contradictory canonical
authority documentation. No authored runtime-logic or dependency boundary is
mixed in.

## Remaining Risks

- PlantUML is pinned; Java, ImageMagick, Pandoc, WeasyPrint, and fonts remain
  environment-provided, so cross-host rendering is not fully hermetic.
- The externally requested phrase "authorization implementation until auth
  proof" is intentionally retained in the chunk contract even though later
  authorization chunks produce that proof; reviewers recorded this as a low
  wording risk rather than an implementation ambiguity.
- Production issuer/JWKS/introspection configuration and legacy actor
  classification remain future chunk inputs.
- This chunk specifies authorization; it does not implement runtime authority.

## Stop Condition

Stop after PR publication for human review. Do not start `WS-AUTH-001-02` or
`WS-POL-002-04` automatically, and do not merge without explicit user approval.
