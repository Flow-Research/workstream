# Internal Review Evidence: WS-ENG-001-01

## Chunk

WS-ENG-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS after fixes | None remaining | Required evidence, reuse/dedup routing, and large-diff risk reviewed. Large bootstrap size accepted because this is one process-infrastructure foundation chunk. |
| qa/test | PASS after fixes | None remaining | Added deterministic Markdown link checker and regression tests for gate helpers. |
| security/auth | PASS WITH LOW RISKS | None | No auth/session/product security behavior changed. CI token permissions are read-only and checkout credentials are not persisted. |
| product/ops | PASS WITH LOW RISKS | None | Product/Ops is first-class and engineering lifecycle remains separate from Workstream product lifecycle. |
| architecture | PASS after fixes | None remaining | Added missing allowed files, kept `.agents`, `.codex`, and `.agent-loop` boundaries separate, and removed brittle review-path handling. |
| ci integrity | PASS after fixes | None remaining | Added workflow permissions, pinned checkout, Markdown/stale checks, regression tests, dirty-tree handling, and stricter evidence validation. |
| docs | PASS after fixes | None remaining | Added aggregate evidence template, deterministic link checker, and PR template parity. |
| reuse/dedup | PASS after fixes | None remaining | Resolved PR trust-bundle drift, reviewer-output drift, sequencing conflict, and reuse/dedup routing. |
| test delta | PASS | None | Added `scripts/test_agent_gates.py`; tests strengthen gate behavior and are wired into CI. |

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

## Commands Run

```bash
python3 -m py_compile scripts/check_internal_review_evidence.py scripts/workstream_agent_gate.py scripts/check_stale_workstream_wording.py scripts/check_markdown_links.py scripts/test_agent_gates.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format markdown
```

## Remaining Risks

- The bootstrap is intentionally large because it installs the initial Codex-native engineering loop in one process-infrastructure chunk.
- The static agent sensor reports `REVIEW_REQUIRED` for this PR, as expected, because it touches process, CI, policy, and reviewer surfaces.

