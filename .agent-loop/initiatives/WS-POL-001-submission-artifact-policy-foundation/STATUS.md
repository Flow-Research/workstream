# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01`, `WS-POL-001-02`, `WS-POL-001-03`, `WS-POL-001-04`,
`WS-POL-001-05`, `WS-POL-001-06`, `WS-POL-001-07`, `WS-POL-001-08`,
`WS-POL-001-09`, `WS-POL-001-10`, and `WS-POL-001-11` are merged to `main`.
The post-actor-registry Terminal Benchmark live API drill passed through real
HTTP calls, but it required DB inspection for project setup outputs and locked
context verification. `WS-POL-001-12` is implemented in PR #76 to expose the
first project setup and project policy visibility APIs. `WS-POL-001-13` and
`WS-POL-001-14` remain the next visibility/finalize chunks before rerunning the
drill without DB inspection.

## Active Chunk

`WS-POL-001-12` is implemented on branch
`codex/ws-pol-001-12-project-setup-policy-visibility` in PR #76. Internal
review is complete, CodeRabbit feedback is being addressed, and the chunk is
not merged until the user explicitly approves PR #76.

## Chunk Status

| Chunk | Status | Branch | PR | Notes |
|---|---|---|---:|---|
| `WS-POL-001-01` | Merged | `codex/ws-pol-001-01-submission-artifact-policy` | 28 | Implements guide-source snapshots, guide sufficiency reports, submission artifact policy, effective project policy, project pre-submit checker contract, activation guards, and key-based artifact policy merge. |
| `WS-POL-001-02` | Merged | `codex/ws-pol-001-02-agent-runtime-compiler` | 61 | Adds async guide sufficiency / derivation agents, runtime port, OpenAI Agents SDK adapter boundary, trusted compiler path, and server-owned provenance guards. |
| `WS-POL-001-03` | Merged | `codex/ws-pol-001-03-task-locked-context` | 63 | Moves task locked-context and submission runtime to the effective policy and project checker bundle. |
| `WS-POL-001-04` | Merged | `codex/ws-pol-001-04-post-submit-policy` | 65 | Splits post-submit checker policy provenance and locks durable checker runs to post-submit policy context. |
| `WS-POL-001-05` | Merged | `codex/ws-pol-001-05-revision-resubmission` | 66 | Proves revision resubmission, real API drill, and `evaluation_pending` lifecycle status. |
| `WS-POL-001-06` | Merged | `codex/ws-pol-001-06-terminal-benchmark-drill` | 67 | Hardens the Terminal Benchmark proof harness and removes stale project guide/payment contracts before continuing pre-submit checker work. |
| `WS-POL-001-07` | Merged | `codex/ws-pol-001-07-task-contract-cleanup` | 68 | Removes task-owned `required_files`/`required_evidence` from request/response/model/migration and keeps artifact requirements project-policy driven. |
| `WS-POL-001-08` | Merged | `codex/ws-pol-001-08-celery-project-setup` | 69 | Makes guide/source capture enqueue Celery pre-submit setup automatically: sufficiency first, blocked stops, draft submission artifact policy next; removes remaining construction-state compatibility surfaces. |
| `WS-POL-001-09` | Merged | `codex/ws-pol-001-09-openai-agent-sdk-only` | 71 | Removes the production `local_fixture` project setup runtime and old runtime selector; keeps deterministic test behavior in explicit test-local fakes only. |
| `WS-POL-001-10` | Merged | `codex/ws-pol-001-10-pre-submit-hardening` | 72 | Hardens duplicate guide-version conflicts, guide-create source snapshots, active-guide checker summaries, worker self-profile onboarding, and failed pre-submit audit evidence. |
| `WS-POL-001-11` | Merged | `codex/ws-pol-001-11-actor-profile-registry-impl` | 74 | Implements local Workstream actor identity and actor profile registries for verified Flow actors before the next live API drill. |
| `WS-POL-001-12` | PR open | `codex/ws-pol-001-12-project-setup-policy-visibility` | 76 | Adds project setup-run and project policy visibility APIs for setup runs, sufficiency reports, submission artifact policies, effective policy, and compiled project pre-submit checker policy; awaiting human merge review after external feedback fixes. |
| `WS-POL-001-13` | Proposed | - | - | Add task work-context, worker submission-requirements, and operator locked-context APIs. |
| `WS-POL-001-14` | Proposed | - | - | Replace public submission lock with finalize, define system actor audit semantics, and rerun the Terminal Benchmark proof without DB inspection. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| PR #76 human merge review | Human reviewer | Review and explicitly approve or request changes for `WS-POL-001-12`. |
| Missing task context visibility APIs | Workstream | Implement `WS-POL-001-13`. |
| Public lock wording and no-DB drill proof | Workstream | Implement `WS-POL-001-14` before rerunning Terminal Benchmark as accepted proof. |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add public revision lifecycle coverage instead of direct `needs_revision` test setup | Test-delta review | High for `WS-POL-001-05` |
| Add focused `0007 -> 0006` downgrade assertion for locked-context columns and constraints | QA/test-delta review | Medium follow-up |
| Extract shared artifact path and forbidden-pattern helpers before further checker-policy expansion | Reuse/dedup review | Medium follow-up |
| Add profile-level audit events if actor/profile changes become reputation-sensitive | Security review on PR #72 | Medium follow-up |
| Rerun Terminal Benchmark live API drill with canonical worker profile setup | Post-merge gate after PR #74 | High |
| Rerun Terminal Benchmark live API drill without direct DB inspection | `WS-POL-001-14` | High |
| Add reviewer packet visibility scoped to eligible/assigned reviewers before full review lifecycle work | Product/ops review on visibility planning | High follow-up |
