# Internal Review Evidence: WS-ENG-001-01

## Chunk

WS-ENG-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS after fixes | None remaining | Required evidence, backend migration/config routing, reuse/dedup routing, and large-diff risk reviewed. Large bootstrap size accepted because this is one process-infrastructure foundation chunk. |
| qa/test | PASS after fixes | None remaining | Added deterministic Markdown link checker and plain-Python regression tests for gate helpers, including missing evidence files and base-ref failures. |
| security/auth | PASS after fixes | None remaining | No auth/session/product security behavior changed. CI token permissions are read-only, checkout credentials are not persisted, workflow interpolation is quoted, and evidence base refs fail closed. |
| product/ops | PASS after fixes | None remaining | Product/Ops is first-class and engineering lifecycle remains separate from Workstream product lifecycle. Engineering-loop policy names no longer collide with product policy names. |
| architecture | PASS after fixes | None remaining | Kept `.agents`, `.codex`, and `.agent-loop` boundaries separate from Workstream product contracts and renamed generic engineering-loop policy files. |
| ci integrity | PASS after fixes | None remaining | Added workflow permissions, pinned checkout, Markdown/stale checks, regression tests, dirty-tree handling, stricter evidence validation, and advisory sensor naming. |
| docs | PASS | None | Verified renamed policy links, Markdown links, stale wording scan, and product/engineering-loop terminology separation. |
| reuse/dedup | PASS after fixes | None remaining | Resolved PR trust-bundle drift, reviewer-output drift, sequencing conflict, reuse/dedup routing, and product/engineering policy wording drift. |
| test delta | PASS | None | `scripts/test_agent_gates.py` now runs without pytest and covers the CodeRabbit/internal reviewer hardening findings. |

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
- CodeRabbit command-injection finding: fixed by moving `github.base_ref` into `BASE_REF` and quoting it in the workflow command.
- CodeRabbit missing/deleted evidence-file finding: fixed with structured missing/unreadable evidence failures and regression coverage.
- CodeRabbit Markdown unreadable/deleted file finding: fixed by skipping unreadable or deleted changed Markdown files.
- CodeRabbit stale-wording matcher finding: fixed with case-insensitive regex patterns for known stale terms.
- CodeRabbit static-sensor base-ref finding: fixed by resolving base refs before diff analysis and reporting `BASE_REF_UNRESOLVED` when no valid ref exists.
- CodeRabbit `numstat` undercount finding: fixed by accumulating additions/deletions per path across committed, staged, and dirty diffs.
- CodeRabbit template nitpicks: fixed conditional reviewer wording, repeatable chunk-map template, flexible remaining-risk template, external review Definition of Done criteria, and explicit merge-approval checklist item.
- Product/engineering boundary risk: fixed by renaming generic engineering-loop policy files to `engineering-review-policy.md`, `human-merge-review-policy.md`, and `repository-engineering-policy.md`, and by clarifying reviewer TOML instructions.
- Internal evidence gate fail-open on configured base refs: fixed by failing closed when `GITHUB_BASE_REF` or `INTERNAL_REVIEW_BASE_REF` cannot resolve.
- Internal evidence gate row validation gap: fixed by requiring reviewer table rows to pass and have no blocking findings.
- Backend migration/config review bypass: fixed by adding Alembic, backend tooling, and demo package files to review routing and static sensor coverage.
- `AGENTS.md` stale-wording blind spot: fixed by scanning `AGENTS.md` except the explicit old-name warning line.
- PR trust-bundle duplication risk: fixed by marking `.agent-loop/templates/PR_TRUST_BUNDLE.md` as canonical and `.github/pull_request_template.md` as a synchronized mirror.

## Commands Run

```bash
python3 -m py_compile scripts/check_internal_review_evidence.py scripts/workstream_agent_gate.py scripts/check_stale_workstream_wording.py scripts/check_markdown_links.py scripts/test_agent_gates.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_internal_review_evidence.py
git diff --check origin/main
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
```

## Remaining Risks

- The bootstrap is intentionally large because it installs the initial Codex-native engineering loop in one process-infrastructure chunk.
- The static agent sensor reports `REVIEW_REQUIRED` for this PR, as expected, because it touches process, CI, policy, and reviewer surfaces.
- Changed-file discovery is still implemented in multiple gate scripts; tests cover the current behavior, and a shared helper can be extracted in a later cleanup chunk if drift appears.
