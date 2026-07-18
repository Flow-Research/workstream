# WS-CON-001-PLAN3 Internal Review Evidence

Reviewed code SHA: a69fad3a32ad47e3bd60a79cd75f5867eefc52b3
Reviewed at: 2026-07-17T18:14:54Z
Reviewer run IDs: auth08_arch_review/final-a69fad3, auth08_qa_product_review/final-a69fad3, auth08_security_review/final-a69fad3

## Reviewed boundary

The exact reviewed snapshot reconciles CON planning with merged AUTH PR #140,
AUTH-09A runtime, and REV PR #128 at trusted `main` `0302bcf`. It authorizes the
provenance-only rebind of the older PLAN/PLAN2 evidence required by the
cumulative PR gate. After that reconciliation, the CodeRabbit repair changes 24
planning-path entries with 713 insertions and 120 deletions relative to
`adf5cc1`. It changes no backend, migration, runtime catalogue, test, script,
workflow, dependency, or merge-intent content.

The reviewed boundary establishes:

- 74 runtime PermissionIds and 65 ActionIds, with nine active and 56 planned;
- no registered CON-specific ActionId and no task-claim ActionId;
- stable PermissionId `task.claim` followed by the safe order AUTH-10/PREP and
  task seam, CON-05A hidden freeze and task composition, then AUTH-13 action
  enumeration/registration/evaluator integration/activation;
- planned `review.claim` and `review.decision` actions gated on the merged
  mandatory CON participant, REV-owned composition, and later AUTH activation;
- exact AUTH-PREP authority-first lock, opaque-handle binding, feature-lock,
  recomposition, single AUTH evaluation, flush-only participant, and
  caller-owned commit semantics;
- 22 explicitly unregistered, non-final CON surface mappings and no speculative
  `AUTH_CON_*` ActionOwner candidates;
- a mandatory CON flush-only participant with a reviewer operation after
  immutable Review/findings/resolutions and lease/queue closure but before the
  decision branch, plus an accept-only submitter operation after exact
  FinalAcceptance and accepted task/assignment effects;
- exact REV-owned FinalAcceptance fields `submission_id`, `recorded_by`, and
  `policy_context_ref`, with submitter contribution sourced only from that fact;
- REV-12A as the sole joint release controller/fence, with every CON
  obligation writer fenced before monotonic root ordinal allocation and
  same-generation at-or-below-cutoff completion during delivery drain;
- `Review(accept) -> FinalAcceptance -> accepted_submission`, with REV as the
  transaction owner, no separate FinalAcceptance action/API, no adjudication
  dependency, and no independent CON commit; and
- one schema-v2 merge intent naming `WS-CON-001-01` as an explicit-start
  same-initiative successor;
- executable, fail-closed verification commands and pass criteria for 16 active
  future chunks, with 78 percent repository and 90 percent focused coverage;
- AUTH registration/context/custody/prepared-port inputs as merged upstream
  prerequisites, never CON-owned acceptance work; and
- optional CON-09B outside `chunks/` as a zero-file deferred proposal requiring
  separate ART/AUTH/human approval and a fresh reviewed replacement contract.

## Reviewer results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | None | The 24-path external repair is cohesive, bounded, executable, and planning-only after all review findings. |
| qa/test | PASS AFTER FIXES | None | Focused selectors, migrations, rollback/race proof, coverage, 08B scope, and deferred 09B semantics pass. |
| security/auth | PASS AFTER FIXES | None | AUTH prerequisites, registration order, fail-closed commands, 09B whitelist, and template CI controls pass. |
| product/ops | PASS AFTER FIXES | None | FinalAcceptance, contribution, compensation, fulfillment cutoff, and no-adjudication behavior remain unchanged. |
| architecture | PASS AFTER FIXES | None | Two-operation sequencing, upstream AUTH ownership, executable gates, 09B deferral, and release control pass. |
| ci integrity | PASS AFTER FIXES | None | No CI/workflow/test/runtime delta or bypass; repository 78 and focused 90 percent floors remain mandatory. |
| docs | PASS AFTER FIXES | None | PR-template structure, external response, review log, allowed scope, canonical names, and provenance are explicit. |
| reuse/dedup | PASS | None | No duplicate runtime abstraction or alternative authorization path is introduced; common AUTH/REV contracts are referenced. |
| test delta | PASS | None | No tests changed; 80 existing agent-gate tests and all static gates pass. |

## Findings and repairs

### Resolved substantive finding

Initial QA and security reviews found that the draft treated `task.claim` as an
existing ActionId. Runtime inspection proved it exists only as a PermissionId.
The plan, discovery, handoff, decisions, status, chunk map, PLAN3 contract, and
CON-05A contract now state that the ActionId remains absent until the hidden
freeze and task composition merge. AUTH-13 alone owns the later enumeration,
registration, evaluator integration, and activation.

### Resolved process finding

The exact-SHA QA re-review found that the PLAN3 contract's evidence criterion
could not be complete until this evidence file and the PR trust bundle existed.
Both were added after review through paths explicitly allowed by the repository
evidence gate; no reviewed planning or implementation file changed afterward.
The final exact-SHA rebind then added the two older evidence paths to PLAN3's
allowed scope so every evidence file added by the cumulative branch can carry
current, parser-complete provenance without rewriting historical conclusions.

### Resolved current-main architecture finding

The first current-main architecture review found that the PLAN3 title still
named only AUTH PR #140 and that its allowed-file list repeated CON-07. The
contract title now matches the AUTH-and-REV current-main merge intent and the
duplicate row is removed. All required reviewers re-ran against exact SHA
`e968430b0c3b5f1432899c9aa31ef209b774eae0`.

### Resolved external-review findings

CodeRabbit's five consolidated threads and description warning were valid at
the contract/process level. The repair:

- adds exact focused commands, non-empty selection, coverage floors, and pass
  criteria to all 16 affected active chunks;
- moves AUTH registration/context/custody/prepared-port requirements to
  upstream prerequisites while retaining registration -> hidden behavior ->
  evaluator/activation ordering;
- moves CON-09B from `chunks/` to `deferred/`, gives it no current allowed
  implementation files, and fail-closes promotion to an exact planning-path
  whitelist;
- aligns CON-08B allowed tests, runtime-verification row, selector, and Ruff
  targets;
- replaces fail-open Git/Ripgrep absence checks with status-sensitive checks;
  and
- mirrors the repository PR template and records the repair in the external
  response and root review log.

Initial internal re-review found and repaired the remaining 04B ordering,
09B whitelist/location, 08B scope, review-log, allowlist, shell-failure, and
trust-template defects. All required tracks then passed exact SHA
`a69fad3a32ad47e3bd60a79cd75f5867eefc52b3`.

### Confirmed non-findings

- A failed same-session/action substitution does not consume an otherwise valid
  prepared handle.
- ServiceIdentity, static-matrix membership, and action availability are
  code-owned validations rather than database lock targets.
- CON imports no AUTH persistence, grant query, evaluator, registration,
  ActionOwner, or availability writer.
- FinalAcceptance has no public API or independent authorization action.
- FinalAcceptance uses REV's canonical `submission_id`, `recorded_by`, and
  `policy_context_ref` names; CON does not redefine the entity.
- REV owns the sole joint release controller/fence; CON adds no parallel
  controller or lifecycle state.
- No adjudication lifecycle or dependency was introduced.
- The archival PDF deletion is user-owned, unstaged, and excluded from every
  reviewed commit.

## Deterministic evidence

```text
python3 scripts/check_markdown_links.py
  PASS - 61 changed Markdown files before evidence refresh
python3 scripts/check_stale_workstream_wording.py
  PASS
python3 scripts/check_stale_authorization_docs.py
  PASS
python3 scripts/check_stale_artifact_contracts.py
  PASS - foundation phase
python3 scripts/check_loop_memory_state.py
  PASS
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q scripts/test_agent_gates.py
  PASS - 80 tests
git diff --check adf5cc1..a69fad3
  PASS
git diff --check
  PASS
external-review repair backend/.github/scripts delta
  none
python3 scripts/update_post_merge_memory.py validate-merge-intent --base-ref origin/main
  PASS - WS-CON-001-PLAN3
```

The circuit-breaker passed with a documentation-only size exception. The full
branch is large because it contains the original reference transcription and
durable planning/review history, but the external repair is one bounded 24-path
planning correction, has no runtime boundary, and required no split.

Valid findings addressed: yes

Open sub-agent sessions: none

## Stop

PLAN3 is reviewed for PR #142 refresh. This evidence authorizes no merge
or CON-01 start. The user retains the human checkpoint and must explicitly
approve PR #142 before merge.
