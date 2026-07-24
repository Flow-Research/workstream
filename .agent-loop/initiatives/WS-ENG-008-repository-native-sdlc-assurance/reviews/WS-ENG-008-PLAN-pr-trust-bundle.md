# PR Trust Bundle

## Chunk

`WS-ENG-008-PLAN` — Repository-Native SDLC Assurance Planning

Merge intent: `.agent-loop/merge-intents/WS-ENG-008-PLAN.json`

## Goal

Establish a reviewed, planning-only initiative for machine-enforced contract
scope, scheduled signed-state auditing, adversarial proof, property testing,
mutation evidence, and lossless review-memory indexing.

## Human-approved intent

- Intent: `../INTENT.md`
- Plan: `../PLAN.md`
- Chunk map: `../CHUNK_MAP.md`

## Signed Start Provenance

- Signed start run: N/A — first-new-initiative planning intake
- Authorized main SHA: `bcf1292e1a591e3e84bf8ee212ee7191d80741fa`
- Phase: planning intake; no active planning or implementation chunk
- Contract path: reviewed contracts `../chunks/WS-ENG-008-01-*.md` through `07`
- Signed contract blob SHA: N/A until post-merge explicit start selects chunk 01
- Reviewed planning SHA: `85bd98d6c55b066c9f1a44bc8aa83514911f4ea0`

Only independently verified signed automation state is canonical authority.
Planning intake records stopped state and cannot authorize implementation.

## What changed

- Added the seven canonical initiative root planning files.
- Added seven sequential L1 implementation contracts.
- Added one schema-v2 PLAN merge intent naming only chunk 01.
- Added the exact required internal review evidence and this trust bundle.

## Why it changed

Workstream's loop is healthy, but ordinary scope remains prose-reviewed, signed
state lacks independent scheduled drift detection, and deeper proof mechanisms
need bounded repository-native ownership.

## Design chosen

One assurance mechanism per PR, ordered by dependency. Contract enforcement
comes first and must upgrade all later ENG-008 contracts. Scheduled audit is
read-only. Adversarial proof uses existing reviewers. Property and mutation
testing are bounded and reproducible. Review memory is archived losslessly last.

## Alternatives rejected

- Immediate global mutation threshold: no calibrated evidence.
- Universal tenth reviewer: duplicates current track ownership.
- Scheduled repair: creates a second state writer.
- Destructive review-log truncation: loses durable evidence.
- Reusing dormant work as authority: violates signed start custody.

## Scope control

The PR adds only one new initiative directory and one PLAN merge intent. It
changes no existing file, workflow, application, test, dependency, permission,
coverage threshold, generated state, or product behavior.

## Product Behavior

- [x] No Workstream product behavior changed.

## Acceptance criteria proof

- [x] Complete intent, discovery, plan, chunk map, status, risks, and decisions.
- [x] Seven bounded contracts with allowed files, prohibitions, measurable proof,
  all required reviewers, human focus, and stop conditions.
- [x] ART/AUTH/REV concurrent state and CON/QUALITY dormant state reconciled.
- [x] Objective scope cutover and successor conversion close self-exemption.
- [x] One merge intent names same-initiative chunk 01 with explicit start true.
- [x] Status claims no active planning or implementation chunk.

## Tests/checks run

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
git diff --check origin/main...HEAD
```

Result: all passed; 100 Agent Gate tests and 14 planning Markdown link checks.

## Test delta

- No tests, workflows, coverage settings, or application files changed.
- The planning contracts specify future tests but implement none.

## CI integrity

- [x] Coverage thresholds unchanged
- [x] Lint/typecheck/test commands unchanged
- [x] No workflow or package-script weakening
- [x] No dependency added
- [x] No unpinned GitHub Action
- [x] Planning intake remains additive and stopped

## Reviewer results

Reviewed planning SHA: `85bd98d6c55b066c9f1a44bc8aa83514911f4ea0`

Reviewer run IDs: `eng008_plan_senior_arch_docs`,
`eng008_plan_qa_ci_tests`, `eng008_plan_security_ops_reuse`

All nine tracks pass after two bounded repair cycles. See
`WS-ENG-008-PLAN-internal-review-evidence.md`.

## External review

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | Review after publication; supplementary only. |
| GitHub checks | Pending | Exact final PR head must pass. |

## Remaining risks

- Concurrent active PRs may advance main and require rebase/re-review evidence.
- Implementation tool choices remain bounded decisions in their owning chunks.
- Human approval of this PR establishes planning only, never a signed start.

## Follow-up work

After merge and successful Automated Merge Memory, stop. Chunk 01 begins only
after an explicit user instruction and successful signed start on exact main.

## Human review focus

- Is contract enforcement first and does it govern contracts 02–07?
- Is scheduled verification structurally read-only?
- Are property/mutation budgets objective and non-weakening?
- Are concurrent initiatives preserved without borrowing their authority?

## Human merge ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
