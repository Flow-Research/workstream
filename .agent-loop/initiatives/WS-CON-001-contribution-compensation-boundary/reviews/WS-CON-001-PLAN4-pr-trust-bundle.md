# PR Trust Bundle: WS-CON-001-PLAN4

## Chunk

`WS-CON-001-PLAN4` — Current-Main Reconciliation.

## Goal and human-approved intent

Refresh the complete CON plan after merged ART, AUTH, REV, XINT, and CON work;
repair stale documents and dependency order; and identify the next bounded CON
runtime change without starting implementation.

## What changed and why

- Refreshed the planning baseline through main `2feaf47d`, including merged REV
  PLAN4 PR #258 and merged ART runtime PR #249.
- Replaced the obsolete dispatcher-first linear order with a capability-based
  partial order: `03A -> 03B`, independent `02C`, then exact REV/CON gates.
- Deferred `02B` until AUTH supplies the complete dispatcher
  identity/action/matrix/context/PREP contract.
- Aligned the CON map, canonical specification, AUTH handoff, joint handoff,
  conformance matrix, risks, decisions, source manifest, and immediate chunk
  contracts.
- Tightened future receipt persistence against raw callback/provider/secret/PII
  storage.

## Design and alternatives

The plan preserves subsystem ownership and one-commit orchestration: AUTH owns
authority, ART owns bytes/provider access, REV owns review lifecycle and the
decision commit, and CON owns policy/contribution/award/fulfillment facts.
Waiting for the dispatcher before independent persistence and moving foreign
behavior into CON were rejected.

## Scope control and product behavior

This is planning/specification work only. It changes no runtime, migration,
route, action availability, workflow, dependency, CI configuration, or test.
The pre-existing user-owned reference-PDF deletion is excluded. Product
behavior remains unchanged.

## Acceptance proof and checks

- Current baseline, runtime absences, open/merged PR state, and migration head
  are recorded from repository/GitHub evidence.
- Canonical and initiative dependency graphs agree with merged REV PLAN4.
- `git diff --check`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 -m unittest -v scripts.test_lightweight_agent_gates`

All listed local checks pass. Hosted Backend currently has the independently
reproduced AUTH concurrency failure described below. No tests or CI controls
changed.

## Reviewer results

- Architecture: PASS after dependency-handoff repair.
- Security/auth: PASS.
- Product/ops: PASS after merged-REV risk wording repair.
- QA/test/CI: PASS WITH CONDITIONS; the user-owned PDF deletion remains
  excluded, and hosted Backend must become green after the current-main push.
- Docs: PASS after correcting source-manifest paths.
- Senior engineering/reuse: PASS after aligning the `06` gate and `03D` scope.

## External review, remaining risks, and follow-up

Agent Gates and CodeRabbit pass on PR #261. The old Backend run failed one AUTH
actor-profile concurrency test also failing on current main; the refreshed
current-main head requires a green rerun or upstream AUTH repair. Four valid
CodeRabbit findings were repaired and recorded in
`WS-CON-001-PLAN4-external-review-response.md`; the refreshed external review
is pending. Migration numbering must be refreshed at implementation start. AUTH registrations,
legacy-row classification, REV runtime targets, and provider/callback contracts
remain future explicit gates.

After PLAN4 merges and human approval, the only recommended implementation is
CON-03A adapter-binding persistence. No later chunk starts automatically.

## Human review focus and merge ownership

Review the corrected partial order, AUTH dispatcher deferral, REV lease and
FinalAcceptance dependencies, receipt data minimization, and excluded PDF.
Only the human may approve and merge this PR.
