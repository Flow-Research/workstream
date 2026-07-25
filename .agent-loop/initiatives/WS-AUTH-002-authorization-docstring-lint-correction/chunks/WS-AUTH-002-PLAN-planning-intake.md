# Chunk Contract: WS-AUTH-002-PLAN — Authorization Docstring Lint Correction Planning Intake

## Parent initiative

`WS-AUTH-002` — Authorization Docstring Lint Correction

## Goal

Land one additive planning tree that declares the narrow corrective successor
without activating or implementing it.

## Why this chunk exists

Trusted explicit starts require a reviewed contract on exact `main`; this
planning-only intake establishes that contract without misusing AUTH-11.

## Approved plan reference

- INTENT: `.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Start phase

`planning`

## Allowed files

```text
.agent-loop/initiatives/WS-AUTH-002-authorization-docstring-lint-correction/**
.agent-loop/merge-intents/WS-AUTH-002-PLAN.json
```

## Not allowed

```text
application, test, migration, API, database, workflow, or configuration changes
active-state claims or implementation
Ruff, docstring, coverage, CI, review, or merge-gate weakening
changes outside one additive initiative tree and one merge intent
```

## Acceptance criteria

- [ ] The PR adds only one canonical initiative planning tree and one schema-v2 merge intent.
- [ ] The intake contains no implementation and leaves the initiative stopped.
- [ ] `WS-AUTH-002-01` is the same-initiative implementation successor and requires explicit start.
- [ ] The implementation contract permits only four named docstrings and corrective evidence.
- [ ] AUTH-11 and every existing initiative remain unchanged.

## Verification commands

```bash
python3 scripts/check_internal_review_evidence.py
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

Confirm this is planning-only, preserves AUTH-11, and makes weakening any lint
or CI gate impossible in the successor.

## Stop conditions

Stop if the intake requires application changes, activates work, modifies an
existing initiative, or weakens any quality gate.
