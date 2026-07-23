# Discovery: WS-ENG-007 - Concurrent PR Review Reconciliation

Discovery was performed read-only against trusted `main` at merge
`9033a97a4be6d762cae4b210018ef81a079395c2`.

## Repository behavior found

- Branch protection requires `agent-gates` and `test`, uses strict up-to-date
  checks, enforces protection for administrators, requires one approval, and
  dismisses stale reviews.
- `.github/workflows/backend.yml` and `agent-gates.yml` run for pull requests;
  neither declares `merge_group`.
- `scripts/check_internal_review_evidence.py` records one reviewed SHA and
  rejects every non-evidence path changed between that SHA and the PR head.
- The evidence gate does not distinguish PR-authored changes from a later base
  merge, does not bind a patch manifest, and cannot preserve reviewer tracks.
- Loop-memory merge records already preserve base/head/tree identities and
  deterministic deltas, providing conventions that can be reused without
  making generated memory a pre-merge authority.

## Relevant files

| Path | Relevance |
|---|---|
| `scripts/check_internal_review_evidence.py` | Current coarse reviewed-SHA invalidation. |
| `scripts/workstream_agent_gate.py` | Computes changed files for PR gate routing. |
| `scripts/test_agent_gates.py` | Deterministic policy tests and synthetic repositories. |
| `.github/workflows/agent-gates.yml` | Required policy check; lacks merge-group trigger. |
| `.github/workflows/backend.yml` | Required backend/fan-in check; lacks merge-group trigger. |
| `.agent-loop/templates/INTERNAL_REVIEW_EVIDENCE.md` | Human-readable review provenance template. |
| `.agent-loop/templates/PR_TRUST_BUNDLE.md` | Human merge summary and CI integrity surface. |
| `.agent-loop/policies/repository-engineering-policy.md` | Canonical review and merge boundaries. |
| `AGENTS.md` | Mandatory agent behavior. |

## Important distinction

GitHub approval dismissal and internal reviewer validity are separate. GitHub
may require a renewed human approval after a branch update. This initiative
does not bypass that rule; it prevents unnecessary internal agent fanout when
the reviewed patch is provably unchanged.

## Closed initial boundary vocabulary

The repository-owned v1 graph classifies every tracked path into one or more of
`workflow_ci`, `auth_security`, `payment_compensation`, `database_schema`,
`shared_interface_contract`, `generated_policy_process`, `product_runtime`,
`tests_coverage`, or `docs_only`. Unmatched, malformed, or ambiguously mapped
paths are `unknown`.

Transitive edges are repository-owned: workflow/CI reaches tests/coverage and
generated process; database/schema reaches consuming runtime, interfaces, and
tests; shared interfaces reach consuming runtime/tests; auth and payment reach
their runtime, interfaces, migrations, audit, and tests; generated process
reaches workflows, schemas, templates, and gates. `unknown` invalidates all
tracks. A PR never authors or narrows this graph.

## Unknowns reserved for later human administration

- Exact GitHub merge-queue repository-setting API behavior.
- Hosted context behavior after queue enablement. These block administrative
  enablement, not repository-side parity planning.
