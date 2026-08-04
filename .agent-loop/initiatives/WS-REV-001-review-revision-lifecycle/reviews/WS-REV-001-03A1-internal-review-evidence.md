# Internal Review Evidence: WS-REV-001-03A1

## Candidate

- Trusted base: `10720382cd9639f00f09578f772b97ab3afc358b`
- Reviewed implementation commit: `a5a778b4c1be2602d406fdf23c05bd8320f1c8cb`
- Scope: hidden REV queue/admission persistence, originally migration 0050 and
  reconciled to migration 0051 after ART PR #249, focused tests,
  data-model documentation, initiative status, and one merge intent
- Runtime exposure: none; no route, checker hook, lease, Review, revision,
  contribution, AUTH, ART, or upstream mutation behavior is added

## Reviewer results

| Track | Result | Resolution |
|---|---:|---|
| Architecture | PASS | Scope includes metadata registration and merge intent; no ownership drift remains. |
| Senior engineering | PASS | Database-owned insert stamps and focused invariant tests resolved the original concerns. |
| QA/test | PASS | Fresh-id replay and all checker-admissibility branches are covered. |
| Product/ops | PASS | The change remains hidden persistence at the `allow_review` boundary. |
| Security/auth | PASS | Exact lineage, immutable identity, delete/truncate refusal, and downgrade safety are database-enforced. |
| Docs | PASS | Data-model wording distinguishes current persistence from later lease behavior. |
| CI integrity | PASS | No workflow or package-script change; no coverage gate was weakened. |
| Reuse/dedup | PASS with low risk | REV-specific repository patterns are appropriate; digest syntax remains locally duplicated to avoid importing an owner-specific AUTH or ART type. |
| Test delta | PASS | Direct constraint, trigger, replay, downgrade, and absence-of-lease proofs are present; no test was weakened or skipped. |

## Findings repaired

- Exact replay no longer depends on reuse of an internal row primary key.
- The contract now explicitly permits central metadata registration and the
  required merge-intent artifact.
- Queue/admission creation timestamps and queue generations are stamped by
  PostgreSQL, preventing caller-controlled queue age.
- Tests now cover non-completed, non-current, non-`allow_review`, checker
  lineage, task/Submission lineage, and project mismatch refusal.
- Direct database tests isolate replay-key, operation, checker-run, digest,
  state-shape, and committed-queue identity constraints.
- Admission-only and queue-only populated downgrade refusal are isolated and
  prove that revision and protected rows survive the failed downgrade.
- The focused coverage command includes the complete new REV package.

## Deterministic evidence

- `backend/.venv/bin/alembic heads`: PASS on the original implementation; after
  reconciliation with ART PR #249, the sole head is the REV successor
  `0051_review_queue_foundation`.
- Isolated `tests/test_alembic.py -k review_queue_foundation`: PASS.
- Isolated `tests/test_review_queue_persistence.py`: PASS, 10 focused tests.
- Isolated `--cov=app.modules.reviews --cov-branch --cov-fail-under=90`: PASS.
- Ruff over the new REV package and focused tests: PASS.
- `python3 scripts/check_stale_review_contracts.py`: PASS.
- `python3 scripts/check_markdown_links.py`: PASS.
- `git diff --check`: PASS.

The full test suite and repository-wide 78 percent coverage floor are reserved
for GitHub Actions, per repository operations guidance and the user instruction.

## Remaining risks and gates

- The same SHA-256 syntax exists in multiple bounded owner modules. Creating a
  cross-owner shared type is not justified inside this REV chunk.
- PostgreSQL validates upstream lineage at the REV write boundary; the queue
  row records that fact and does not constrain future upstream-owned mutation.
- GitHub Actions, CodeRabbit, and human review remain pending.
- Merge does not start 03A2.

## Disposition

PASS for PR publication after the evidence-only documentation delta receives
its final narrow review. No reviewer session may remain open at publication.
