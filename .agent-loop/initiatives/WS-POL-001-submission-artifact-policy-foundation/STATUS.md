# Status: WS-POL-001 - Submission Artifact Policy Foundation

## Current Status

`WS-POL-001-01` through `WS-POL-001-16` are merged to `main`.
`WS-POL-001-16` completed the final clean Terminal Benchmark live API drill
through real HTTP calls, using sanitized source material and a worker packet
derived from the live `submission-requirements` response. Evidence is recorded,
reviewed, privacy-scrubbed, rendered as a professional PDF report, and merged
through PR #84.
`WS-POL-001-14` replaced public submission lock wording with finalization,
defined system actor audit semantics, and merged PR #79's HTTP-visible Terminal
Benchmark proof evidence. The accepted post-merge no-DB Terminal Benchmark
drill from `main` exposed a self-conflicting agent-derived submission artifact
policy. Corrective chunk `WS-POL-001-15` hardened the derivation contract and
reran that accepted drill successfully before merging through PR #81.

## Active Chunk

None. `WS-POL-001` is complete through `WS-POL-001-16`.

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
| `WS-POL-001-12` | Merged | `codex/ws-pol-001-12-project-setup-policy-visibility` | 76 | Adds project setup-run and project policy visibility APIs for setup runs, sufficiency reports, submission artifact policies, effective policy, and compiled project pre-submit checker policy. |
| `WS-POL-001-13` | Merged | `codex/ws-pol-001-13-task-context-apis` | 77 | Adds task work-context, worker submission-requirements, and operator-only locked-context APIs. |
| `WS-POL-001-14` | Merged | `codex/ws-pol-001-14-submission-finalize` | 79 | Replaces public submission lock with finalize, defines system actor audit semantics, scopes operator visibility, and proves the Terminal Benchmark flow through HTTP-visible lifecycle responses. |
| `WS-POL-001-15` | Merged | `codex/ws-pol-001-15-agent-derivation-hardening` | 81 | Hardens agent-derived submission artifact policy instructions after the no-DB Terminal Benchmark drill exposed a required-artifact/forbidden-pattern self-conflict. |
| `WS-POL-001-16` | Merged | `codex/ws-pol-001-16-terminal-benchmark-live-api-drill` | 84 | Proved a human-visible Terminal Benchmark drill through real HTTP APIs without DB inspection as lifecycle proof; merged as `a3d2a3f`. |

## Blockers

| Blocker | Owner | Next action |
|---|---|---|
| none | none | none |

## Follow-Ups

| Item | Source | Priority |
|---|---|---|
| Add public revision lifecycle coverage instead of direct `needs_revision` test setup | Test-delta review | High for `WS-POL-001-05` |
| Add focused `0007 -> 0006` downgrade assertion for locked-context columns and constraints | QA/test-delta review | Medium follow-up |
| Extract shared artifact path and forbidden-pattern helpers before further checker-policy expansion | Reuse/dedup review | Medium follow-up |
| Add profile-level audit events if actor/profile changes become reputation-sensitive | Security review on PR #72 | Medium follow-up |
| Add reviewer packet visibility scoped to eligible/assigned reviewers before full review lifecycle work | Product/ops review on visibility planning | High follow-up |
