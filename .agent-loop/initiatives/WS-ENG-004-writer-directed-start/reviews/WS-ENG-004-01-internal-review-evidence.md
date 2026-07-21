# WS-ENG-004-01 Internal Review Evidence

Reviewed code SHA: `710b97d0c6220aafc0007a2282457f6d3e1e55e7`

Reviewed against trusted main: `70f9c7bcdb63680e545f661a956929379df138e4`

Reviewed at: `2026-07-21T13:22:50Z`

Reviewer run IDs: `writer_start_senior_arch_docs`,
`writer_start_qa_ci_tests`, `writer_start_security_ops_reuse`

CI-repair reviewer run ID: `writer_start_ci_security_ops_reuse`

## Scope

Writer-directed reviewed-contract starts, trusted contract phase, current
repository-permission authority, global-idle/completed-work guards, independent
exact-tree checking, cancellation preservation, and exact one-target bootstrap.

## Deterministic evidence

- `ruff check scripts/update_post_merge_memory.py scripts/check_loop_memory_state.py scripts/test_update_post_merge_memory.py scripts/test_check_loop_memory_state.py` — pass.
- GitHub-equivalent checker coverage command — 206 passed; 90.18 percent
  branch coverage; unchanged 90 percent floor passed.
- `python3 scripts/test_agent_gates.py` — 88 passed.
- `python3 scripts/check_stale_workstream_wording.py` — pass.
- `python3 scripts/check_markdown_links.py` — pass for 18 changed Markdown files at the CI-repair reviewed SHA.
- `git diff --check` — pass.

## Reviewer results at the reviewed code SHA

Reviewer runs: plan=`writer_start_plan_review`; senior/architecture/docs=`writer_start_senior_arch_docs`; QA/CI/test-delta=`writer_start_qa_ci_tests`; security/product-ops/reuse=`writer_start_security_ops_reuse`.

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | PASS | None | CI repair remained test/evidence-only and the prior runtime findings remain repaired. |
| QA/test | PASS | None | Added hostile selection, exact evidence, lifecycle, cancellation, and recovery proofs. |
| Security/auth | PASS | None | Trusted Git supplies phase; current write permission is signed; cancel/recovery remain closed. |
| Product/ops | PASS | None | Exact-SHA re-review confirmed that the committed evidence and trust bundle resolve the local-only evidence finding. |
| Architecture | PASS | None | Contract evidence comes from exact Git objects; immutable audit and lifecycle boundaries remain separate. |
| CI integrity | PASS | None | Exact-tree checks were strengthened; no test, coverage, permission, or failure gate was weakened. |
| Docs | PASS | None | Contributor and operator guidance covers permission, phase, completion, cancellation, and bootstrap behavior. |
| Reuse/dedup | PASS | None | Existing helpers are reused; generator/checker separation is intentional independent validation. |
| Test delta | PASS | None | No tests were removed, skipped, or weakened; hostile regression coverage increased. |

## Repairs made from review

- Replaced mutable worktree traversal with exact Git tree and blob resolution.
- Rejected completed chunk identities and globally concurrent planning or implementation.
- Added contract-declared planning/implementation phase and rejected ambiguity.
- Replaced the static actor list with current GitHub `write`/`push`, `maintain`, or `admin` permission evidence under a closed trusted-main policy.
- Added independent exact historical main/path/blob/title/phase checking.
- Expanded v2 recovery proof through first-parent binding, consumption, projections, manifest, ledger, and replay.

Open sub-agent sessions: none

Valid findings addressed: yes

The evidence-publication finding was addressed by committing this file and the
PR trust bundle, then re-reviewing their exact immutable SHA. External GitHub
checks, CodeRabbit, and explicit human approval of the specific PR remain before
merge.

The later CI repair was reviewed at exact SHA `710b97d0c6220aafc0007a2282457f6d3e1e55e7`.
All nine tracks passed with no blocker; the repair adds meaningful fail-closed
branch tests and does not change runtime authority or weaken the coverage gate.
