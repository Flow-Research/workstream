# External Review Response: WS-POL-001-01

## PR

https://github.com/Flow-Research/workstream/pull/26

## Chunk

`WS-POL-001-01`

## Source

CodeRabbit, GitHub checks, and human PR review.

## Summary

External review feedback is tracked separately from internal sub-agent evidence.
Internal sub-agent results live in
`WS-POL-001-01-internal-review-evidence.md`.

## External Findings

| Source | Finding | Severity | Status | Response |
|---|---|---:|---:|---|
| CodeRabbit | `WS-POL-001-03` acceptance criteria repeated no-side-effect wording. | Low | Fixed | Consolidated the no-row, no-version, no-transition, and no-durable-checker-run guarantee without weakening it. |
| Human review | Project owners must not author or approve Workstream internal `SubmissionArtifactPolicy`; Workstream derives it from open-ended project material and `admin` or `project_manager` approves the internal bundle. | High | Fixed | Updated planning artifacts, ADRs, glossary, architecture docs, specs, templates, operating manual, data flow, and first user flows. |
| Human review | Project-guide material is open-ended, not a fixed checklist; Workstream must run sufficiency and derivation agents internally. | High | Fixed | Added `ProjectGuideSufficiencyAgent`, `GuideSufficiencyReport`, and `SubmissionArtifactPolicyDerivationAgent` to the plan, ADR, data model, lifecycle, templates, and chunk map. |
| Human review | `PreSubmitCheckerPolicy` must be persisted and locked, not derived on read. | High | Fixed | Updated plan, ADRs, data model, lifecycle, checker flow, and chunk contracts to require persisted project checker compiled bundle provenance. Tasks lock the project checker bundle hash; they do not compile their own checker. |
| Human review | Pre-submit failures should not use review decisions and should show pass/fail/warning details like the Snorkel-style static checker experience. | High | Fixed | Standardized `pre_submission_checker_failed` with structured pass/fail/warning details and explicit exclusion of `accept`, `needs_revision`, and `reject`. |
| Human review | Current planning PR must be mergeable before implementation starts. | High | Fixed | Updated status, chunk map, chunk contract, proof obligations, and review evidence while keeping backend implementation inactive. |
| CodeRabbit | ADR 0011 described pre-submit/review-decision separation but did not state how implementation must prove enforcement. | Major | Fixed | Added an implementation enforcement contract to ADR 0011. It explicitly says this PR is planning-only and lists the API, UI/demo, persistence, database, and chunk-level proof required before implementation chunks can close. |
| CodeRabbit | `docs/architecture_checker_framework.md` made `pre_submission_checker_failed` read like the response type instead of the failure condition represented by a failed pre-submit response. | Minor | Fixed | Reworded the checker framework to require `PreSubmitCheckResponse(status="failed", eligible_to_submit=false, results=[...])` for blocking failures, with `pre_submission_checker_failed` described as the user-facing failure condition rather than a response field. |
| Human review | Downstream reports and policies were bound to `guide_version` but not the exact guide/source snapshot. | High | Fixed | Added `GuideSourceSnapshot`, `source_snapshot_id`, and `source_snapshot_hash` to the plan, ADR, data model, chunk map, chunk contract, and templates. Guide/source changes now invalidate reports, policies, acknowledgements, approvals, effective policies, and checker bundles. |
| Human review | Chunk 1 claimed task/checker runtime removals while forbidding task/checker modules. | High | Fixed | Re-scoped Chunk 1 to guide-source snapshots, project policy records, effective project policy merge, append-only lifecycle, and activation guards. Moved compiler behavior to Chunk 2 and task-field/runtime migration to Chunk 3. |
| Human review | Project-level policy should not become per-task policy generation. | High | Fixed | Corrected the architecture to the realistic model: one project guide/effective policy/project pre-submit checker reused by tasks. `ProjectGuideSufficiencyAgent` must block activation if the guide does not cover the task set. |
| Human review | Effective policy merge semantics were not executable enough. | High | Fixed | Added per-field deterministic merge rules for union, intersection, logical OR, minimum limits, platform-locked hash algorithm, restrictive packaging merge, and setup-conflict blocking. |
| Human review | URL ingestion and durable source identity were conflated. | Medium | Fixed | Split temporary approved-adapter fetch locators from durable sanitized source refs. Ordinary URL query parameters can be used for approved retrieval; signed URLs, credentials, token-bearing refs, and local paths cannot be persisted as source identity. |
| Human review | API contract for `pre_submission_checker_failed` was ambiguous. | High | Fixed | Locked separate paths: preflight returns `200 PreSubmitCheckResponse`; blocked submission creation returns `422 DomainError(code="pre_submission_checker_failed")` with structured details. |
| Human review | Approved policies and compiled bundles needed append-only lifecycle rules. | High | Fixed | Added `draft -> approved -> superseded` lifecycle, immutable approved/superseded rows, supersedes pointers, and `compiled_bundle` as canonical JSON source of truth with derived index projections only. |
| Human review | PR body still asked whether `evidence_policy` should remain as a compatibility alias and whether pre-submit policy should derive on read. | Medium | Fixed | Removed stale human-review questions from the PR body. The current plan says no `evidence_policy` compatibility alias and no derive-on-read runtime path. |
| Human review | Prior edits overcorrected into task-level checker generation. | High | Fixed | Removed per-task policy/checker generation from the plan. Chunk 2 persists the project `PreSubmitCheckerPolicy`; Chunk 3 only locks task references to the project guide, effective policy, and checker bundle hash. |
| Human review | `GuideSourceSnapshot` looked like a single source ref instead of a guide material bundle. | High | Fixed | Updated the data model, ADR, plan, chunk map, chunk contract, and template to model `GuideSourceSnapshot` as a canonical manifest bundle with per-item source records and a bundle hash. |
| Human review | Remaining schema details were ambiguous: size fields, hash algorithm, dual status fields, and source snapshot hash consistency. | High | Fixed | Added `maximum_file_size_bytes` and `maximum_package_size_bytes`, locked `artifact_hash_algorithm` to platform `sha256`, normalized policy lifecycle to `lifecycle_status`, and documented `source_snapshot_hash` as server-derived from the snapshot bundle hash. |
| Human review | New guide snapshots needed an explicit fairness boundary for already locked tasks. | High | Fixed | Added the protective rule: a new guide-source snapshot invalidates setup records for new activation and unlocked tasks only; already locked tasks retain their context unless explicitly rebased through audit. |
| Human review | Rejected per-task policy fields still appeared in the Chunk 5 submission spec. | High | Fixed | Removed the stale task-binding and task-effective-policy provenance fields; submissions now keep only project-scoped locked policy/checker provenance. |
| Human review | Chunk wording still allowed project checker generation to be read as task-scoped. | High | Fixed | Normalized active docs to say generated project pre-submit checker policy/bundle and expanded the stale-model scan to include snake-case per-task-policy terms. |
| Human review | Final activation boundary needed to be explicit. | High | Fixed | Locked the final architecture: guide activation requires a compiled project `PreSubmitCheckerPolicy`; Chunk 2 turns that complete activation gate on after compiler execution exists. |
| Human review | Bundle hash canonicalization was under-specified. | High | Fixed | Added `sha256(canonical_json(manifest_json))` with UTF-8, sorted keys, deterministic source-item ordering, volatile-field exclusions, and duplicate source item rejection. |
| Human review | Checker compiler needed a semantic completeness invariant. | High | Fixed | Added the requirement that every enforceable effective project policy rule must produce deterministic checker logic, and the compiler must reject omitted rules, weakened severity, skipped evidence rules, missing platform defaults, or untraceable bundle rules. |
| Human review | Task-specific runtime parameters could become a hidden per-task policy channel. | High | Fixed | Constrained v0.1 runtime parameters to trusted task-contract fields only; no free-form parameter map is allowed and parameters cannot override checks, severity, storage, forbidden artifacts, hash algorithm, or platform defaults. |
| CodeRabbit | Some docs still referenced guide version, shortened policy hash names, or generic policy names where immutable guide-source snapshot and effective project submission artifact policy were required. | Minor | Fixed | Updated first-user flow, chunk map, chunk contract, lifecycle, and roadmap wording to use immutable guide-source snapshot, `SubmissionArtifactPolicy`, and effective project submission artifact policy hash consistently. |
| CodeRabbit | Source snapshot item Markdown table used raw pipe characters inside the source-kind placeholder. | Minor | Fixed | Replaced pipe separators with slash separators so the table remains valid Markdown. |
| CodeRabbit | Rejected-model stale-wording patterns for PascalCase symbols were case-sensitive. | Minor | Fixed | Made the relevant stale-wording regexes case-insensitive while preserving the existing regression test coverage. |
| Human review | `SCREENING -> READY` operations docs omitted guide source snapshot id/hash, effective project submission artifact policy hash, and pre-submit checker bundle hash. | High | Fixed | Updated queue policy and task locked-context docs so `READY` requires those locked references before workers see tasks. |
| Human review | The planning PR scope was easy to confuse with the later backend implementation chunk scope. | High | Fixed | Added explicit planning PR scope exceptions and renamed future backend scope headings to implementation allowed/not-allowed files. |
| Human review | "Most tasks" wording left a loophole for task-specific checker generation. | High | Fixed | Changed the contract to every task under the same active project guide version reusing that guide version's project `PreSubmitCheckerPolicy`; uncovered task sets block activation or split into another project/guide. |
| Human review | Submission packet provenance omitted locked guide-source snapshot id/hash and effective project submission artifact policy hash. | Medium | Fixed | Updated the submission packet template and submission spec provenance to include server-derived guide-source snapshot id/hash, effective project submission artifact policy hash, and checker bundle hash. |
| Human review | Checker docs still described `check_evidence_present` reading `task.required_evidence`. | Medium | Fixed | Updated the checker spec so evidence requirements come from the locked project `PreSubmitCheckerPolicy` and effective project submission artifact policy. |
| Human review | Activation summaries omitted immutable guide-source snapshot in local lists. | Medium | Fixed | Updated architecture lockdown, operating manual, data flow, and queue docs to include immutable guide-source snapshot in activation and readiness gates. |
| Human review | Project setup checklist marked guide active before the full activation bundle. | Low | Fixed | Reordered the checklist so guide activation follows sufficiency, approved policy, effective project submission artifact policy hash, generated checker, checker bundle hash, post-submit checker, review, revision, payment, and reviewer setup. |
| Internal review | Final reviewer pass recorded low residual risks but no blockers. | Low | Documented | Internal evidence records exact reviewed SHA, reviewer run IDs, local proof commands, and residual risks separately from external review response. |

## Commands To Re-Run After Push

```bash
gh pr view 26 --json number,title,state,isDraft,url,reviewDecision,reviews,comments,statusCheckRollup
python3 scripts/check_internal_review_evidence.py
python3 scripts/check_loop_memory_state.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/test_agent_gates.py
git diff --check
```

## Final External Review State

```text
latest local agent gate result: REVIEW_REQUIRED, with internal review evidence supplied
latest local evidence gate: pass after evidence refresh
latest local loop memory, Markdown links, stale wording, agent gate tests, and diff checks: pass
GitHub checks and CodeRabbit must be re-read after every push before merge
```
