# Chunk Contract: WS-ART-001-PLAN3 — v0.1 End-to-End Reconciliation

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Planning only

## Goal

Audit current main and make every remaining ART/AUTH/REV/CON dependency,
ownership boundary, PR boundary, and v0.1 completion proof explicit.

## Allowed Files

WS-ART planning artifacts and future contracts; WS-XINT-002 planning artifacts
needed to correct dependency order; related specifications and review evidence;
and only the independent custody expectation fixture in
`backend/tests/test_authorization.py` when a reviewed custody split changes the
exact documentation-to-catalogue parity assertion.

## Not Allowed Changes

Application code, migrations, workflows, action availability, grants, provider
configuration, or successor implementation.

## Acceptance Criteria

- merged guide work and the subsequently merged AUTH-04B implementation are
  stated accurately;
- every future L1 chunk has one durable/security boundary;
- pre-submit materializer activation precedes contributor preparation;
- reviewer packet and contribution identity handoffs have explicit owners;
- reviewer evidence upload and client delivery are not implied v0.1 work;
- exact remaining order, stop conditions, and final conformance are documented.

## Verification Commands

Every successor contract inherits this exact minimum and must add its mapped
focused module before implementation begins; descriptive test prose alone is
not sufficient:

```bash
(cd backend && .venv/bin/python -m ruff check app tests scripts)
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

| Chunk | Required focused test module(s) |
|---|---|
| `04A1` | `tests/test_artifact_architecture.py`, `tests/test_alembic.py` |
| `04A2` | `tests/test_submission_archive.py` (including the canonical `PreparedArtifact.inspect(...)` scratch-custody and cleanup seam) |
| `04A3` | `tests/test_submission_manifest.py`, `tests/test_submission_change_gate.py` |
| `04B` | `tests/test_submission_precheck.py`, `tests/test_checker_materialization.py` |
| `04C1`-`04C2` | `tests/test_submission_bundle_admission.py`, `tests/test_artifact_verification.py`, `tests/test_artifact_recovery.py` |
| `05A`-`05B` | `tests/test_submission_concurrency.py`, `tests/test_submissions.py`, `tests/test_alembic.py` |
| `06A`-`06B` | `tests/test_checker_materialization.py`, `tests/test_checkers.py` |
| `07A` | `tests/test_review_artifacts.py`, `tests/test_artifact_materialization.py` |
| `07B` | `tests/test_contributions.py`, `tests/test_review_lifecycle.py` |
| `08A`-`08C` | Provider conformance, API drill, AUTH parity, and migration suites named in the existing 08/XINT-08 contracts. |

Each materially changed subsystem must pass focused `--cov-fail-under=90`.
The exact PR head must pass hosted `Backend / test` at the repository-wide 78
percent floor and `Agent Gates / agent-gates`; the local machine need not run
the full backend suite.

## Required Reviewers

Architecture, security/auth, product/ops, QA, senior engineering, CI integrity,
docs, reuse/dedup, and test delta.

## Human Review Focus And Stop Conditions

Confirm the finish line and corrected AUTH order. Stop after planning; every
implementation chunk requires a separate human start.
