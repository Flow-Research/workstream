# Internal Review Evidence: WS-ENG-001-01

## Chunk

WS-ENG-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: b22b940ee50956c9c7bfd0e681ffac727b6ff82c

Reviewed at: 2026-06-18T19:28:12Z

Reviewer run IDs: 019edbb9-9998-7db1-8060-06bfad8b85ae, 019edbbb-b2aa-7583-9cdc-db03a280135a, 019edbbe-d103-7493-a972-8efcb4c277c9, 019edbc2-c418-7fa3-851c-32a06a69644e, 019edbef-dd1d-7a12-825d-5ac49b123716, 019edc29-f00b-7641-90b4-2e11188a47b3

After this reviewed SHA, only evidence and status files changed.

External review response: `.agent-loop/initiatives/WS-ENG-001-codex-zero-trust-loop-bootstrap/reviews/WS-ENG-001-01-external-review-response.md`

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None remaining | Required evidence, backend migration/config routing, reuse/dedup routing, large bootstrap size, reviewed-SHA binding, optional reviewer-row validation, and parser hardening reviewed. |
| qa/test | PASS WITH LOW RISKS | None remaining | Deterministic gate tests cover reviewed SHA binding, PR_HEAD_SHA, dirty tree branches, exact result values, N/A notes, demo routing, stale wording scope, and parser edge cases. |
| security/auth | PASS WITH LOW RISKS | None remaining | No auth/session/product security behavior changed. PR_HEAD_SHA is bound in CI, provenance placeholders fail closed, N/A bypass is blocked, and post-review files are allowlisted. |
| product/ops | PASS | None | Product/Ops is first-class, the engineering lifecycle remains separate from Workstream product lifecycle, and status/trust-bundle wording is reconciled. |
| architecture | PASS AFTER FIXES | None remaining | Kept `.agents`, `.codex`, and `.agent-loop` boundaries separate from Workstream product contracts and aligned template/runtime post-review path wording. |
| ci integrity | PASS AFTER FIXES | None remaining | Added workflow permissions, pinned checkout, Markdown/stale checks, regression tests, dirty-tree handling, stricter evidence validation, reviewed-SHA binding, and PR_HEAD_SHA wiring. |
| docs | PASS | None | Verified renamed policy links, Markdown links, stale wording scan, and product/engineering-loop terminology separation. |
| reuse/dedup | PASS AFTER FIXES | None remaining | Resolved PR trust-bundle drift, reviewer-output drift, sequencing conflict, reuse/dedup routing, and product/engineering policy wording drift. |
| test delta | PASS | None | `scripts/test_agent_gates.py` now runs without pytest and covers internal gate hardening findings. |

## Valid Findings Addressed

- Product/Ops missing from templates: fixed in chunk contract, PR trust bundle, review finding template, GitHub PR template, skill, and reviewer config.
- Local evidence gate could pass stale evidence: fixed by comparing against `origin/main` or explicit base and by including dirty-tree paths.
- Evidence gate required only baseline reviewers: fixed by deriving required focused reviewers from changed paths.
- Evidence validation was substring-only: fixed by requiring `open sub-agent sessions: none`, `valid findings addressed: yes`, and a changed chunk ID when a chunk contract changes.
- Static sensor ignored uncommitted work: fixed by including staged, unstaged, and untracked files.
- Workflow token permissions were implicit: fixed with `permissions: contents: read`.
- Markdown link check was ad hoc and local-only: fixed with `scripts/check_markdown_links.py`, base-ref awareness, and CI wiring.
- Stale wording scan was self-matching: fixed with `scripts/check_stale_workstream_wording.py`.
- Gate behavior lacked regression coverage: fixed with `scripts/test_agent_gates.py` and CI wiring.
- `scripts/test_agent_gates.py` was not routed to test delta: fixed by adding `test_*.py` detection to the evidence gate.
- PR trust-bundle drift: fixed by aligning reusable template, skill, and GitHub PR template around product behavior, CI integrity, external review, follow-up work, and explicit user merge approval.
- Reviewer output-contract drift between skills and TOML wrappers: fixed by making TOML reviewers defer to skill output format where relevant.
- Gate sequencing conflict: fixed by distinguishing deterministic proof checks before fanout from internal review evidence validation after fanout.
- Reuse/dedup routing inconsistency: fixed in routing and budget policies.
- New `agent-gates` workflow rationale unclear: documented as a process-only PR gate for loop/docs/Codex-surface changes.
- Product/engineering boundary risk: fixed by renaming generic engineering-loop policy files to `engineering-review-policy.md`, `human-merge-review-policy.md`, and `repository-engineering-policy.md`, and by clarifying reviewer TOML instructions.
- Internal evidence gate fail-open on configured base refs: fixed by failing closed when `GITHUB_BASE_REF` or `INTERNAL_REVIEW_BASE_REF` cannot resolve.
- Internal evidence gate row validation gap: fixed by requiring reviewer table rows to pass and have no blocking findings.
- Backend migration/config review bypass: fixed by adding Alembic, backend tooling, and demo package files to review routing and static sensor coverage.
- `AGENTS.md` stale-wording blind spot: fixed by scanning `AGENTS.md` except the explicit old-name warning line.
- PR trust-bundle duplication risk: fixed by marking `.agent-loop/templates/PR_TRUST_BUNDLE.md` as canonical and `.github/pull_request_template.md` as a synchronized mirror.
- Internal reviewer findings on evidence provenance: fixed by requiring reviewed code SHA, reviewed-at timestamp, reviewer run IDs, PR head SHA validation, and stale reviewed-SHA invalidation for non-evidence changes.
- Internal reviewer findings on reviewer routing/check precision: fixed by routing demo UI source paths, requiring exact reviewer result values, enforcing N/A notes, and narrowing stale wording checks to obsolete Workstream names plus forbidden Codex-incompatible paths.
- Internal reviewer findings on gate parsing and artifact separation: fixed placeholder provenance acceptance, template/runtime post-review path mismatch, optional reviewer-row validation, unrelated Markdown table false positives, PR_HEAD_SHA success-path coverage, and external-review response separation.

## Follow-Up Review Wave

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| QA/test | PASS | None | Verified patched globals restore through assertion failures and stale-wording assertion is order-independent. |
| docs/product-ops | PASS | None | Verified Medium-finding and product wording scope wording does not blur Workstream runtime with the Codex engineering loop. |
| senior engineering | PASS | None | Verified the four late CodeRabbit nitpicks are handled without scope creep or brittle tests. |
| final security/auth | PASS | None | Verified PR_HEAD_SHA binding, provenance validation, N/A bypass prevention, post-review path controls, stale wording path enforcement, and no auth/runtime leakage. |
| final product/ops/docs | PASS | None | Verified product/runtime separation and template/runtime consistency; stale evidence required this final evidence/status commit. |
| final parser hardening | PASS | None | Verified adjacent unrelated Markdown tables no longer create false reviewer rows and optional reviewer rows are exact-result validated. |
| artifact separation senior engineering | PASS WITH LOW RISKS | None | Verified external review response files do not satisfy internal evidence and templates/protocol separate review layers. |
| artifact separation QA/test | PASS WITH LOW RISKS | None | Verified complete internal evidence plus external response passes, external-only response fails for code changes, and missing evidence uses internal-evidence filename convention. |
| artifact separation security/auth | PASS | None | Verified fail-closed behavior remains and no product/auth/runtime behavior changed. |
| artifact separation product/ops/docs | PASS WITH LOW RISKS | None | Verified human review path now separates internal sub-agent evidence from external CodeRabbit/GitHub response artifacts. |

## Commands Run

```bash
python3 -m py_compile scripts/check_internal_review_evidence.py scripts/workstream_agent_gate.py scripts/check_stale_workstream_wording.py scripts/check_markdown_links.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_internal_review_evidence.py
git diff --check origin/main
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_agent_gates.py
git diff --check
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check f3ed9af..6042c44
```

## Remaining Risks

- The bootstrap is intentionally large because it installs the initial Codex-native engineering loop in one process-infrastructure chunk.
- The static agent sensor reports `REVIEW_REQUIRED` for this PR, as expected, because it touches process, CI, policy, and reviewer surfaces.
- Changed-file discovery is still implemented in multiple gate scripts; tests cover the current behavior, and a shared helper can be extracted in a later cleanup chunk if drift appears.
- The final evidence/status commit is intentionally limited to allowlisted files after the reviewed SHA.
