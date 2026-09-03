# Chunk Contract: WS-AUTH-001-PLAN - Authorization Service Planning

## Parent initiative

`WS-AUTH-001` - Workstream Authorization Service

## Goal

Adopt the user-provided reference specifications as planning inputs, reconcile
them with the current repository, record human decisions, and produce a
migration-aware PR-sized implementation plan without changing runtime code.

## Why this chunk exists

Authorization, actor identity, migrations, audit, project scope, and every
protected product surface are affected. Implementation cannot begin safely
without explicit boundaries and dependency order.

## Approved plan reference

- Human adoption decisions in `DECISIONS.md`
- Repository engineering loop in `AGENTS.md`

## Risk class

L0 - human-led architecture, auth-model, and data-model direction. D1-D3 were
approved by the user on 2026-07-11; D4-D10 remain an explicit approval gate
before implementation activation. The resulting bounded implementation chunks
are L1.

## SLA

P1

## Allowed files

```text
docs/reference_specs/**
.gitattributes
.agent-loop/initiatives/WS-AUTH-001-workstream-authorization-service/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/STATUS.md
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/CHUNK_MAP.md
```

## Not allowed

```text
backend application code, migrations, dependencies, tests, CI
canonical README/architecture/ADR changes before the first implementation chunk
review, contribution, compensation, frontend, or WS-POL implementation
```

## Acceptance criteria

- All eight supplied files are preserved in the repository with matching
  checksums recorded in `SOURCE_MANIFEST.md`.
- `docs/reference_specs/README.md` labels the imported files as immutable
  archival inputs, records the `/api/v1` override, and points to the future
  reconciled canonical specification without changing the eight hashed files.
- Git attributes mark only the imported reference PDFs as binary so repository
  diff/review tooling never decodes PDF bytes as UTF-8 text.
- Intent, discovery, decisions, risks, plan, status, and chunk map are explicit.
- Every implementation chunk has allowed files, exclusions, acceptance
  criteria, verification, reviewers, human focus, and stop conditions.
- The plan preserves `/api/v1`, prevents dual authority, handles legacy actor
  classification fail-closed, and pauses `WS-POL-002-03`.
- Required internal plan reviews pass and all valid findings are resolved or
  documented.
- The plan distinguishes approved L0 direction from proposed L0 decisions and
  does not activate `WS-AUTH-001-01` without explicit approval of D4-D10.

## Verification commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
sha256sum -c docs/reference_specs/SHA256SUMS
git check-attr diff merge text -- docs/reference_specs/*.pdf | awk '$3 != "unset" { exit 1 }'
git diff --check
```

## Required reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- CI integrity
- test delta

## Human review focus

Review the authority precedence, migration safety, chunk size/order, `/api/v1`
decision, WS-POL pause, and proof strategy.

## Stop conditions

Stop if planning requires runtime edits, secrets, production data, inferred
legacy subject kind, or a second authority system.
