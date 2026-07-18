# Chunk Contract: WS-POL-002-05 - Terminal Benchmark Post-Submit Live API Proof

## Parent Initiative

`WS-POL-002` - Post-Submit Checker Foundation

## Approved Plan Reference

- INTENT: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/CHUNK_MAP.md`

## Risk class

L1

## SLA

P1

## Problem Being Solved

The implementation must be proven as a real operator/worker flow, not only by
unit tests. The proof must show the generated post-submit policy setup and the
runtime checker gate through APIs.

## Goal

Run a privacy-safe Terminal Benchmark-style live API drill that proves
post-submit policy derivation, approval, task locking, finalization, checker
routing, `needs_revision`, fixed resubmission, and `review_pending`.

## Target Behavior

- Project setup captures sanitized source material.
- Sufficiency passes or blocks before post-submit derivation.
- Post-submit derivation input/output is visible through setup APIs.
- Compiled post-submit policy hash is visible before activation.
- Activation requires the approved compiled post-submit policy.
- Task locks that policy context.
- Submission finalization runs the locked policy.
- A clean path reaches `review_pending`.
- A worker-fixable post-submit failure reaches `needs_revision`.
- A fixed resubmission returns to `review_pending`.

## Allowed Files

```text
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/**
.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/**
.agent-loop/LOOP_STATE.md
.agent-loop/WORK_QUEUE.md
.agent-loop/REVIEW_LOG.md
docs/roadmap_status.md
examples/terminal_benchmark/**
scripts/privacy_scan_evidence.py
```

The exact `scripts/privacy_scan_evidence.py` path is allowed so this chunk can
add the committed privacy scan used by the verification command. Broader
`scripts/**` edits remain out of scope.

## Not Allowed

```text
backend/app/**
backend/alembic/versions/**
backend/tests/**
backend/scripts/**
frontend or demo UI work
payment/reputation/blockchain settlement
private source identifiers in committed evidence
database inspection as lifecycle proof
```

## Acceptance Criteria

- Evidence shows every lifecycle step through API-visible request/response
  facts.
- Evidence includes post-submit derivation input and output summaries.
- Evidence includes compiled post-submit policy hash and approved status.
- Evidence reads back approval provenance, setup context, source snapshot id,
  source snapshot hash field presence/shape, and compiled policy hash field
  presence/shape through APIs. Committed evidence must show field presence/shape
  or approved redacted placeholders for actor/source/setup identifiers, and must
  redact exact source and policy hash values as `sha256:<redacted>`.
- Evidence proves clean finalization to `review_pending`.
- Evidence proves worker-fixable post-submit failure to `needs_revision`.
- Evidence proves checker-caused `needs_revision` has
  `outcome_source = auto_checker` and no human review decision id.
- Evidence proves fixed resubmission back to `review_pending`.
- Evidence proves internal setup/retry routes remain hidden from workers.
- Evidence proves operator-visible internal repair routes include bounded
  reason, owner, next action, retry eligibility, and audit event id.
- Evidence is privacy-safe and contains no raw local paths, source-specific task
  identifiers, raw source hashes, raw policy hashes, credentials, or replayable
  private refs.
- Privacy scan rejects exact source and policy hashes while allowing approved
  redacted provenance placeholders such as `sha256:<redacted>`.
- A professional PDF report is generated when evidence volume exceeds a concise
  Markdown review packet.

## Verification Commands

```bash
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/api_contract_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test .venv/bin/python scripts/week2_api_e2e.py)
(cd backend && WORKSTREAM_DATABASE_URL=postgresql+asyncpg://workstream:workstream@localhost:5433/workstream_test OPENAI_API_KEY=\"${OPENAI_API_KEY:?set OpenAI key}\" WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL=\"${WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL:?set model}\" WORKSTREAM_TERMINAL_BENCH_FIXTURE=\"${WORKSTREAM_TERMINAL_BENCH_FIXTURE:?set fixture}\" WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT=\"${WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT:-}\" .venv/bin/python ../examples/terminal_benchmark/terminal_benchmark_api_e2e.py)
python3 -m py_compile scripts/privacy_scan_evidence.py
(cd backend && .venv/bin/python -m ruff check ../scripts/privacy_scan_evidence.py)
python3 scripts/privacy_scan_evidence.py .agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews
git diff --check
```

Prerequisites:

- local Postgres test database `workstream_test`
- backend dependencies installed in `backend/.venv`
- `OPENAI_API_KEY` set in local shell only; never committed
- `WORKSTREAM_PROJECT_AGENT_OPENAI_AGENT_SDK_MODEL` set to the approved local
  OpenAI Agents SDK model for the drill
- `WORKSTREAM_TERMINAL_BENCH_FIXTURE` set to the sanitized local fixture path
- `WORKSTREAM_TERMINAL_BENCH_GUIDE_ROOT` set when the fixture needs a separate
  guide-material root
- local API/worker execution configured exactly as the drill command requires
- only redacted evidence committed under
  `.agent-loop/initiatives/WS-POL-002-post-submit-checker-foundation/reviews/`

If `scripts/privacy_scan_evidence.py` does not exist when this chunk starts,
the chunk must add it or replace it with an equivalent committed privacy scan
script before evidence is accepted.

## Required Reviewers

- senior engineering
- QA/test
- security/auth
- product/ops
- architecture
- docs
- reuse/dedup
- test delta
- CI integrity

## Human Review Focus

- Confirm the report proves behavior through APIs without DB inspection.
- Confirm Terminal Benchmark material is used only as a sanitized example.
- Confirm post-submit checker policy is project-scoped and deterministic.
- Confirm worker-facing lifecycle remains clear.

## Stop conditions

Stop and escalate if:

- scope must expand beyond allowed files
- architecture direction changes
- auth/payment/policy/data boundary changes beyond this contract
- CI/test weakening is required to pass
- the same blocker remains after 2 repair attempts
- secrets or production data are needed
