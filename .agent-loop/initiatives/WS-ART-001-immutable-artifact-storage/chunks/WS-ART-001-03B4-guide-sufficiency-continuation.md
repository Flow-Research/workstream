# Chunk Contract: WS-ART-001-03B4 — Guide Sufficiency Continuation

Initiative: `WS-ART-001` | Risk: L1 | Status: Approved for implementation

Merged prerequisites: 03B1, 03B2, 03B3A, 03B3B1, 03B3B2, 03B3B3A,
03B3B3B, 03B3B3C, 03B3B3D, and 03B3B4.

## Goal

Continue the existing Celery project-setup workflow with complete verified,
same-generation canonical guide material and exact persisted provenance.

## Allowed Files

- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/PLAN.md`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/DECISIONS.md`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/RISKS.md`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/STATUS.md`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/AUTH_HANDOFF.md`
- `.agent-loop/initiatives/WS-ART-001-immutable-artifact-storage/CHUNK_MAP.md`
- this chunk contract and its review/trust-bundle files;
- `docs/spec_artifact_storage_service.md`;
- `docs/architecture_data_model.md`;
- `backend/app/interfaces/project_agents.py` and
  `backend/app/interfaces/artifact_operations.py`;
- `backend/app/modules/artifacts/guide_sufficiency_material.py` (new narrow
  artifact-owned query/validation adapter);
- `backend/app/modules/artifacts/models.py` only for the exact extraction-usage
  composite uniqueness needed by provenance foreign keys;
- `backend/app/modules/projects/models.py`, `repository.py`, `schemas.py`, and
  `service.py` for setup orchestration and report provenance;
- `backend/app/modules/projects/setup_queue.py` and the existing Celery
  project-setup execution module for the pre-submit identifier payload;
- `backend/app/modules/projects/guide_mutation_router.py` to dispatch that exact
  committed generation;
- `backend/app/modules/projects/guide_mutation_service.py` to carry the exact
  generation across the post-commit dispatch boundary;
- `backend/app/adapters/project_agents/openai_agent_sdk.py` so the runtime sends
  the same canonical bytes that setup hashes and caps;
- one new Alembic revision after `0045_guide_source_metadata_authority.py`;
- `backend/tests/test_projects.py`, `backend/tests/test_guide_bindings.py`,
  `backend/tests/test_artifact_architecture.py`, and `backend/tests/conftest.py`
  for the canonical isolated-database table inventory;
- `backend/scripts/run_test_lanes.py` only if the new focused test selection must
  be registered without weakening an existing lane.

## Not Allowed

- bytes, extracted content, scratch paths/handles, prepared authorization, or
  credentials in Celery payloads; direct provider access; raw binary/excerpts
  as authoritative input; policy derivation after incomplete extraction;
  legacy-field removal; AUTH availability edits.

The existing post-submit continuation is outside this payload change and keeps
its effective-policy and checker-policy identifiers. This chunk changes only
the pre-submit guide-sufficiency Celery message. The legacy source-material
path remains available for the existing live setup flow until 03C; it must not
be used by the new hidden verified continuation.

## Locked Design

- Every item in the immutable source snapshot is required in v0.1. There is no
  optional-item flag. Every item needs one current-generation binding and one
  successful, policy-current extraction usage.
- Text-family, PDF, DOCX, PPTX, CSV, XLSX, Markdown, plain-text, and JSON outputs
  enter the bounded textual material. PNG/JPEG/WebP output enters only as typed
  structural metadata and cannot satisfy textual semantics. No legacy durable
  ref, CID, caller excerpt, or raw binary enters authoritative material.
- An artifact-owned `GuideSufficiencyMaterialPort` performs all joins over ART
  binding, content, classification, attempt, extracted-content, and usage rows.
  Project services consume only its immutable DTO and never import or query ART
  persistence models.
- Each item DTO contains source item id/order/kind, binding id, original content
  id/hash/byte count, classification id/format, extraction attempt/usage/content
  ids, extractor name/version, extraction-policy version, canonical-output hash,
  omission facts, and exactly one of canonical text or typed structural metadata.
- Canonical agent bytes are the exact compact sorted-key UTF-8 JSON prompt sent
  by the runtime. Every ordered item contains the fixed
  `UNTRUSTED_GUIDE_SOURCE_DATA` label; no caller-selectable delimiter is used.
  The 12 MiB limit counts the complete prompt, including trusted guide context,
  labels, JSON punctuation, escaping, and separators. `12 * 1024 * 1024` bytes
  passes; one byte more fails before agent invocation.
- Agent-created sufficiency provenance is normalized. The report stores setup
  run id, setup generation, assembled-material SHA-256, and byte count. A child
  usage row per item stores report id, item order, source item id, binding id,
  original content id, extraction usage/attempt/content ids, and canonical-output
  SHA-256. Composite foreign keys bind each child to one exact ART usage lineage;
  report/item order and report/extraction usage are unique.
- Immediately before agent invocation, the adapter locks and validates the exact
  draft guide, latest snapshot, setup run/generation, every snapshot item, and
  every ART lineage row. Immediately before report commit the same facts are
  locked and revalidated and the material digest must match. Report, provenance
  children, and setup-run output reference commit once or all roll back.
- The new verified continuation is hidden and callable only with bounded test
  authority until AUTH-04B. It does not silently replace the live legacy setup
  continuation in this chunk. 03C owns that cutover.

## Acceptance Criteria

- the pre-submit project-setup Celery payload is exactly project, guide,
  snapshot, setup run, and setup generation identifiers;
- the project-setup executor reloads and revalidates current
  project/guide/snapshot/run/generation,
  complete bindings, content, and extraction provenance before agent invocation
  and again before report commit;
- all required items must have successful policy-compatible extraction;
- artifact incident, missing/corrupt/stale/unsupported/failed extraction stops
  setup with an internal status and creates no insufficiency decision;
- agent input is bounded canonical content only, never raw binaries or caller
  excerpts, and reports preserve exact content/extraction provenance;
- source content is explicitly delimited/labeled as untrusted data, supplies no
  tools/provider/secret authority, and prompt-injection fixtures cannot override
  system/developer policy or the typed sufficiency output contract;
- `setup_blocked` exposes the stable redacted error codes and remediation defined
  by D46 for `unsupported`, `ambiguous`, `malformed`, `limit_exceeded`,
  `parser_failure`, `cancelled`, and `artifact_incident`, with bounded Operator
  incident reference only for ART incidents;
- canonical agent material is capped at 12 MiB; an exact-boundary assembly may
  proceed, a one-over assembly records `guide_source_limit_exceeded`, and no
  agent call or partial report occurs;
- duplicate or stale Celery execution cannot create or overwrite current output;
- test-only fixed authority proves the complete hidden pipeline while composed
  live binding/read remains deny-only until AUTH-04B;
- changed subsystems remain at least 90% covered and repository coverage stays
  at least 78%.

## Verification

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
(cd backend && .venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/ws-art-03b4.json --timeout-seconds 900 -- .venv/bin/python -m pytest tests/test_projects.py tests/test_guide_bindings.py tests/test_artifact_architecture.py -q --cov=app --cov-report=term-missing --cov-fail-under=0)
(cd backend && .venv/bin/coverage report --precision=2 --fail-under=78)
(cd backend && .venv/bin/coverage report --include='app/modules/projects/*,app/modules/artifacts/guide_sufficiency_material.py,app/*ers/project_setup.py' --precision=2 --fail-under=90)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/test_agent_gates.py
git diff --check
```

The exact PR head must pass hosted `Backend / test` and `Agent Gates / agent-gates`.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.
