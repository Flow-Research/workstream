# Chunk Contract: WS-QUAL-002-05 — Changed-Line-Aware Mutation Reactivation

## Parent initiative
`WS-QUAL-002` — Behavior Ownership Catalogue
## Goal
Reactivate mutation through protected catalogue ownership and exact changed-line
selection, then prove AUTH no longer pauses.
## Why this chunk exists
This delivers reusable ownership without restoring retired callable-wide mutation.
## Approved plan reference
- INTENT: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/INTENT.md`
- PLAN: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/PLAN.md`
- CHUNK_MAP: `.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/CHUNK_MAP.md`
## Risk class
L1.
## SLA
P1.
## Allowed files
```text
backend/scripts/mutation_policy.py
backend/tests/test_mutation_policy.py
backend/scripts/behavior_ownership.py
backend/tests/test_behavior_ownership.py
.github/workflows/behavior-mutation.yml
CONTRIBUTING.md
docs/operations_backend_testing.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/STATUS.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/chunks/WS-QUAL-002-05-mutation-reactivation.md
.agent-loop/initiatives/WS-QUAL-002-behavior-ownership-catalogue/reviews/WS-QUAL-002-05-*
```
## Not allowed
```text
backend/app/**; migrations; global or callable-wide mutation; scores; exemptions; PR authority for existing ownership; test weakening; .github/workflows/mutation-pilot.yml
```
## Acceptance criteria
- [ ] Existing callables resolve from the catalogue physically loaded from the exact protected base SHA, never from PR head, without manual claims.
- [ ] The selection contract adds exact changed executable line/span data beside each containing callable, and the mutation runner consumes those spans—not callable names alone—when constructing final mutation input.
- [ ] Selection contains only changed executable spans and their exact containing callables; unchanged executable lines fail closed if selected.
- [ ] Negative tests prove that a one-line executable change selects only that line, never unchanged executable sibling lines in the same callable.
- [ ] Negative tests inspect the runner's final mutation input and reject unchanged executable lines, callable-wide/full-callable selectors, and any new workflow reference to the retired `mutation-pilot.yml`.
- [ ] A blocking pre-reactivation scan rejects active workflow, script, or configuration references to retired callable-wide workflow paths, selectors, or claim authority.
- [ ] New/remapped callables require additive validated PR-head records and cannot replace protected records.
- [ ] Effective selection resolves each validated `supersedes_behavior_id` before building mutation input and yields exactly one reviewed owner for every changed executable span; zero or multiple owners fail closed.
- [ ] Selection tests reject remaps with missing protected absence/rename proof, nonexistent PR-head locations, narrowed carry-forward evidence, or attempts to delete or replace protected ownership.
- [ ] PR data that deletes, narrows, downgrades, changes tests/outcomes/boundaries, or otherwise replaces existing protected reviewed ownership fails closed.
- [ ] Negative tests prove forged PR-head ownership cannot affect protected-base selection and exact callable custody remains authoritative.
- [ ] AUTH rehearsal and hosted mutation pass within the current cap.
- [ ] The retired `mutation-pilot.yml` workflow remains absent and unreferenced.
- [ ] Historical `.ci/behavior-claims/**` data remains inactive; no workflow, selector, or contributor command reads it as mutation authority.
- [ ] The new workflow emits one stable PR check on every pull request, has no workflow-level path filter, and resolves unrelated changes through an internal `not_applicable` preflight before mutation dependencies install or execute.
- [ ] Human explicitly approves mutation reactivation.
## Verification commands
```bash
(cd backend && .venv/bin/python -m pytest -q tests/test_behavior_ownership.py tests/test_mutation_policy.py)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_lightweight_agent_gates.py
git diff --check origin/main...HEAD
```
## Required reviewers
Architecture, senior engineering, QA, security, product/ops, CI integrity, docs, reuse/dedup, and test delta.
## Human review focus
Protected engineering-gate custody, changed-line selection, additive flow, AUTH
usability, and hosted runtime.
## Stop conditions
Stop if catalogue is incomplete, AUTH still needs routine claims, unchanged
lines enter selection, or the retired 05M workflow would be restored.
