# Chunk Contract: WS-POL-003-01 - Unified Contract and Catalogue Projection

Status: Proposed, inactive. Risk: L1.

## Goal

Add strict unified input/result/evidence models and read-only projections from
ART-04B1's complete pre-submit catalogue and CHECKER/POL's durable post-submit
capability truth. No model call, persistence, registry, or lifecycle change.

## Allowed files

`backend/app/interfaces/project_agents.py`, canonical ART and CHECKER/POL
projection interfaces/composition only, focused tests, and WS-POL-003 docs.

## Not allowed

ART/CHECKER catalogue changes, duplicate project registry, database/model/Celery
changes, action activation, or checker execution.

## Acceptance

- Strict bounded schemas reject extra/executable/unsafe fields.
- ART platform coverage is non-selectable. Pre-submit project capabilities come
  only from ART-04B1; post-submit project capabilities come only from the
  canonical durable CHECKER/POL source.
- `GuideEvidenceRef` is closed and raw excerpts/URLs/paths cannot enter it.
- Optional representative task context does not gate compilation.
- Unknown/default/wrong-stage bindings fail closed.

## Verification and review

Focused schema/catalogue tests, Ruff, type checks, stale-registry scan. Required
reviewers: architecture, security, QA, product, reuse, test delta, CI integrity.
Human focus: no second registry and no executable model fields.
