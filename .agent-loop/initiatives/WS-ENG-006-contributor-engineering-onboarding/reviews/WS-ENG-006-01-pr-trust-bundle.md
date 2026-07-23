# PR Trust Bundle

## Chunk

`WS-ENG-006-01` — Canonical Human And Agent Contribution Entry

Merge intent: `.agent-loop/merge-intents/WS-ENG-006-01.json`

## Goal

Give every human and agent one public, consistent, enforced route into
Workstream repository engineering without relaxing signed starts, evidence,
review, human merge ownership, or automated memory.

## Human-approved intent

- Intent: `../INTENT.md`
- Chunk contract: `../chunks/WS-ENG-006-01-canonical-contribution-entry.md`

## Signed Start Provenance

- Signed start run: https://github.com/Flow-Research/workstream/actions/runs/30007287555
- Authorized main SHA: `9c3ea09f32dc1217dcaaf68cbfcf5ac71aad8805`
- Phase: `implementation`
- Contract path: `.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/chunks/WS-ENG-006-01-canonical-contribution-entry.md`
- Signed contract blob SHA: `afac8131c28efa55a8d1ad0b96049904aefe35ac`
- Reviewed implementation SHA: `4c53f06c7889bbee85bfdce3a5440380eb6ae045`

Only independently verified signed automation state is canonical authority.
These fields are navigation evidence, not authorization.

## What changed

- Added root `CONTRIBUTING.md` with the complete human/agent procedure and a
  public GitHub issue intake for contributors without write permission.
- Reconciled canonical loop, initiative-local concurrency, v0.1, and Automated
  Merge Memory wording across entry docs and policy.
- Added matching signed-start provenance fields to both PR trust templates.
- Added semantic Agent Gate fixtures and negative mutations for policy drift.
- Added one null-successor schema-v2 merge intent.

## Why it changed

The strict loop was enforceable but difficult for a newcomer to discover, and
several public surfaces retained stale loop or time-box wording. Existing work
also needed a safe adoption path that could preserve contribution without
granting retroactive authority.

## Design chosen

One operational root guide links canonical policy and runbooks. A public issue
preserves proposals as discovery input; a maintainer must establish reviewed
artifacts on trusted main, dispatch the exact signed start, adopt only in-scope
work, and run the complete evidence/review path. Stable semantic tests protect
policy outcomes without comparing entire documents.

## Alternatives rejected

- Allowing an unsigned patch PR was rejected because it bypasses start custody.
- Depending on private chat was rejected because it is not public durable intake.
- Copying the complete policy into every document was rejected because it would
  create competing sources of truth.

## Scope control

All 11 implementation files are explicitly allowed by the chunk contract. No
workflow, permission, signer, generator, state schema, application, dependency,
coverage, package, or product-lifecycle file changed.

## Product Behavior

- [x] No Workstream product behavior changed.

## Acceptance criteria proof

- [x] Root guide distinguishes repository and product Contributors and provides
  exact before-work, implementation, pre-PR, merge, and stop procedures.
- [x] Existing patches are preservation/discovery only, never authorization.
- [x] Public GitHub issue intake and the five-step maintainer adoption path are explicit.
- [x] Entry docs use Automated Merge Memory and initiative-local concurrency.
- [x] Manual memory PRs and automatic successor starts remain prohibited.
- [x] Both templates expose the same six signed-start provenance fields.
- [x] Positive fixtures and negative mutations protect every required drift class.
- [x] Exactly one null-successor schema-v2 merge intent is present.

## Tests/checks run

```bash
python3 scripts/update_post_merge_memory.py validate-merge-intent --repository-root . --base-ref origin/main
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 -m py_compile scripts/test_agent_gates.py
git diff --check origin/main...HEAD
```

Result: all passed; 100 Agent Gate tests and 9 changed-Markdown link checks.

## Test delta

- Added semantic positive assertions and negative mutations for contributor
  entry, loop, concurrency, patch adoption, public maintainer adoption, signed
  authority, Automated Merge Memory, exact-head human merge, and template parity.
- No test was removed, skipped, weakened, or rewritten to accept broken behavior.

## CI integrity

- [x] Coverage threshold unchanged
- [x] Lint unchanged
- [x] Typecheck unchanged
- [x] No workflow weakening
- [x] No package script weakening
- [x] No unpinned new GitHub Action
- [x] Checkout credential persistence unchanged

## Reviewer results

Reviewed code SHA: `4c53f06c7889bbee85bfdce3a5440380eb6ae045`

Reviewer run IDs: `eng006_senior_arch_docs`, `eng006_qa_ci_tests`, `eng006_security_ops_reuse`

All nine required tracks passed. QA/test and test delta passed after the
operational-procedure mutation gap was fixed. Senior engineering, architecture,
and docs accepted one Low editorial-maintenance risk.

## External review

External review response file:
`.agent-loop/initiatives/WS-ENG-006-contributor-engineering-onboarding/reviews/WS-ENG-006-01-external-review-response.md`

| Source | Status | Notes |
|---|---:|---|
| CodeRabbit | Pending | Review after publication. |
| GitHub checks | Pending | Exact final PR head must pass. |

## Remaining risks

Policy-critical semantic markers may require test changes during future harmless
editorial rewrites; those changes will remain visible and reviewed.

## Follow-up work

None in this initiative. Automated Merge Memory must stop after this merge;
there is no same-initiative successor.

## Human review focus

- Confirm no sentence permits unsigned work or retroactive patch authorization.
- Confirm the public no-write path is usable without private chat.
- Confirm semantic tests protect policy without locking unrelated prose.

## Human merge ownership

- [ ] I can explain what changed.
- [ ] I can explain why it changed.
- [ ] I know what could break.
- [ ] I accept the remaining risks.
- [ ] The user explicitly approved this specific PR for merge.
