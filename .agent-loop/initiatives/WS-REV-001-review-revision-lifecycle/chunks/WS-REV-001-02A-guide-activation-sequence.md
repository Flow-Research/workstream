# Chunk Contract: WS-REV-001-02A - Guide Chronology And Task Locking Split

## Goal

Convert the oversized guide chronology, publication fencing, and Task guide
stamping proposal into separately executable L1 children. This parent records
the current-main dependency proof and the reviewed split only; it makes no
runtime, schema, migration, workflow, API, or product-document change.

## Why This Split Exists

Preimplementation review on trusted main
`8d5eb15b384fd75787ce98a099400a1d335d2560` found that the former contract
combined a repository-wide project/setup writer fence, canonical-human guide
activation chronology, two database migrations, Task screening composition,
and persistent coverage changes. Those boundaries cannot receive adequate
schema, concurrency, authorization, and rollback proof in one reviewable PR.

## Risk Class

L1 planning/specification for later schema, migration, concurrency,
authorization-lineage, and CI work.

## Current-Main Dependency Proof

- AUTH-09D-A merged through PR #148 at
  `99ae4c963e53f317175dcb308b9e47c93ccf19ed` with migration
  `0026_actor_profile_lifecycle`.
- `WS-AUTH-001-CONTRIBUTOR-FOUNDATION` merged through PR #153 at
  `8d5eb15b384fd75787ce98a099400a1d335d2560` from reviewed PR head
  `6a70b33fee0c63da8893fca35da967d59d3d410a`. Its final reviewed code
  candidate is `0ca5a6326a893e6671848dacde484b7c784b7bd0`.
- PR #153 clean-cuts TaskAssignment and Submission ownership to
  `contributor_id`, adds ActorProfile foreign keys and reusable
  `public.require_human_actor_profile_reference()`, and proves active-human
  transaction revalidation without changing authorization availability.
- PR #153 Backend, Agent Gates, and CodeRabbit checks passed. Its internal
  evidence records real-PostgreSQL migration, direct-SQL, lifecycle race, API,
  rollback, and coverage proof.
- The sole Alembic head on this start base is
  `0027_contributor_foundation`. No child reserves a later revision before its
  own current-main start refresh.

## Publication Rebase Proof

Before merge, this planning branch rebased without conflict onto ART PR #154
merge `44f2467cedc266d2efe261119cfff436ac6b7715`. The sole publication-base head
is now `0028_artifact_admission`. ART #154 changes no Project/setup writer file,
so the planned 02A1 inventory remains complete for this publication snapshot.
This does not pre-authorize a child: 02A1 and every migration-owning successor
must refresh the then-current writer inventory and Alembic head at its own
explicit start.

## Child Sequence

```text
WS-REV-001-02A
-> WS-REV-001-02A1 Project And Setup Publication Fence
-> WS-REV-001-02A3 Guide Activation Chronology
-> WS-REV-001-02A4 Task Guide Triplet And Screening
```

`WS-REV-001-02A2` remains the separately planned post-08 hidden prepared
superseded-guide reactivation chunk. This split does not renumber, start, or
change that later boundary.

## Allowed Files

```text
.agent-loop/initiatives/WS-REV-001-review-revision-lifecycle/**
.agent-loop/merge-intents/WS-REV-001-02A.json
```

## Not Allowed

```text
backend/**
.github/**
docs/reference_specs/**
active product documentation outside the REV initiative
AUTH, ART, or CON owner initiative artifacts
runtime, schema, migration, test, route, action, permission, or availability changes
```

## Acceptance Criteria

- Current-main AUTH dependency evidence and sole migration head are exact.
- The parent is marked non-executable and the three children have complete
  allowed files, prohibited changes, database/locking contracts, acceptance
  criteria, verification, required reviewers, and stop conditions.
- Project/setup fencing precedes chronology so public activation cannot race an
  unfenced setup writer.
- Chronology precedes Task triplet backfill so every non-draft Task can resolve
  one exact guide activation sequence.
- Existing `WS-REV-001-02A2` reactivation remains deferred after chunk 08 and
  does not become part of these children.
- Merge intent names only `WS-REV-001-02A1`, requires a separate human start,
  and starts no runtime automatically.

## Verification

```bash
(cd backend && .venv/bin/docstr-coverage --config .docstr.yaml)
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_stale_authorization_docs.py
python3 scripts/check_stale_review_contracts.py
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/check_markdown_links.py
python3 scripts/check_loop_memory_state.py
python3 scripts/check_internal_review_evidence.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 backend/.venv/bin/python scripts/test_agent_gates.py
backend/.venv/bin/python scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
git diff --check
```

## Required Reviewers

Senior engineering, QA/test, security/auth, product/ops, architecture, docs,
reuse/dedup, test delta, and CI integrity.

## Human Review Focus

Split boundaries, dependency order, exact database ownership, command-specific
lock order, canonical-human semantics, migration refusal/downgrade safety, and
the explicit-start gate before 02A1.

## Stop Condition

Merge, let automated memory record this parent split, and stop. Do not implement
or start 02A1, 02A3, 02A4, 02A2, or 02B from this chunk.
