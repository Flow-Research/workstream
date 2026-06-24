# Internal Review Evidence: WS-POL-001-01

## Chunk

WS-POL-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 9099b60533ba49eb3232fdf505dc17c69c8cbdad

Reviewed at: 2026-06-24T11:38:57Z

Reviewer run IDs: 019ef3df-a4ae-71f0-b50c-dbd99e65af6c, 019ef3e0-cc78-7583-abd8-826f77b6d435, 019ef3e2-d1fc-7642-b079-561bf61b3d07, 019ef3e5-1e10-78f2-b272-f06200c50334, 019ef3e7-6f3d-7730-a2fd-adc55e496811, 019ef3ea-b44c-7741-9ced-b05bb6a5e5d2, 019ef432-a806-75c1-96ac-11c93eea2f9c, 019ef45d-540a-71e1-9531-19277d5450ed, 019ef45f-a5fa-7721-b9ae-aa39b1f6778e, 019ef462-b086-7923-a03e-78c298316f73, 019ef466-2433-7bf3-9335-069cfa5b5838, 019ef46a-171d-7b42-9795-773132754ff0, 019ef46e-dcea-7423-aa46-47a27b098c85, 019ef51b-8491-7192-a868-f2cbc1c56079, 019ef51d-cc5d-7d40-b5e6-0966c546e465, 019ef520-eea1-71c0-919a-63d24728ff32, 019ef523-f173-7e71-8685-902518610fda, 019ef52a-1da8-7df2-9428-c96b1b0cc164, 019ef5c5-db38-76a1-8617-4572f7ebc7a2, 019ef5c7-2666-7e73-9147-4544265a3818, 019ef5c9-2749-75b2-819d-d7018f2b0e12, 019ef5cb-cc57-7151-b2ec-0f0d49ed0fb1, 019ef92b-9da7-7140-878a-1b12c6ed5cd9, 019ef92c-c0a4-7922-8a8c-7257ddb20919, 019ef92e-95d3-72d3-8519-c6ef83548bf8, 019ef930-f548-7dc1-beb4-b055c1f10363, 019ef933-f0a4-7ad3-a882-9a45b9e9b638, 019ef937-5144-7190-b4c5-f83af54de620, 019ef95b-77c6-7331-8dab-e3e7e9207f7a

After reviewed SHA `9099b60533ba49eb3232fdf505dc17c69c8cbdad`, only review evidence and loop status artifacts changed.

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None remaining | Confirmed no backend implementation started. Requested stale evidence refresh, removal of derived-on-read risk, and locked-policy wording in runtime docs. Fixed. |
| QA/test | PASS AFTER FIXES | None remaining | Requested Postgres-backed FastAPI/API proof for Chunk 1 and per-chunk verification expectations. Fixed. |
| security/auth | PASS AFTER FIXES | None remaining | Required project-owner material to be treated as untrusted input, with unsafe refs and embedded tool instructions rejected. Fixed. |
| product/ops | PASS AFTER FIXES | None remaining | Required full activation bundle wording, approved policy provenance, and no manual bypass of derivation agent. Fixed. |
| architecture | PASS AFTER FIXES | None remaining | Required activation docs to include `GuideSufficiencyReport` and effective policy hash, and fixed review-policy wording in the flow diagram. Fixed. |
| docs | PASS AFTER FIXES | None remaining | Required loop state refresh and active guide-policy bundle alignment in docs/templates. Fixed. |
| test-delta | PASS AFTER FIXES | None remaining | Required API-level proof obligations for Chunk 1 warning acknowledgement/provenance and Chunk 4 worker response filtering. Fixed. |
| focused senior engineering | PASS | None | Re-reviewed ADR 0011 enforcement contract and confirmed it does not falsely claim backend enforcement. |
| focused QA/test | PASS AFTER FIXES | None remaining | Found missing UI/demo ownership and schema/persistence proof assignment. Fixed in ADR 0011 and Chunk 4 proof obligations. |
| focused security/auth | PASS | None | Re-reviewed ADR 0011 fail-closed API/database contract and planning-only caveat. |
| focused product/ops | PASS | None | Confirmed worker-facing pre-submit language remains separate from review decisions. |
| focused architecture | PASS AFTER FIXES | None remaining | Confirmed boundaries and requested stale evidence refresh. Fixed by this evidence update. |
| focused docs | PASS WITH LOW RISKS | None | Confirmed ADR and external-review wording are clear and do not overclaim implementation. |
| checker compiler architecture | PASS | None | Confirmed agents derive constrained specs and Workstream owns deterministic compiled checker bundles. |
| checker compiler security/auth | PASS WITH LOW RISKS | None | Requested `admin` or `project_manager` approval of exact future extension code hash after validation and sandbox checks. Fixed. |
| checker compiler QA/test | PASS AFTER FIXES | None remaining | Requested proof for primitive allowlisting, unknown primitive rejection, canonical hash binding, immutable bundle behavior, no executable code fields by default, and future extension gate. Fixed. |
| checker compiler product/ops | PASS WITH LOW RISKS | None | Confirmed the workflow preserves setup-agent assistance, deterministic runtime checking, and admin/project_manager approval. |
| checker compiler docs | PASS AFTER FIXES | None remaining | Confirmed wording consistency and requested evidence refresh. Fixed by this evidence update. |
| response-contract senior engineering | PASS AFTER FIXES | None remaining | Requested external review response wording to match the corrected `PreSubmitCheckResponse` shape. Fixed. |
| response-contract QA/test | PASS AFTER FIXES | None remaining | Verified the architecture doc matches `backend/app/modules/checkers/schemas.py` and requested evidence refresh. Fixed. |
| response-contract security/auth | PASS AFTER FIXES | None remaining | Confirmed pre-submit failure remains separate from review decisions and requested evidence refresh. Fixed. |
| response-contract product/ops | PASS AFTER FIXES | None remaining | Confirmed operator-facing wording is clear and requested external review artifact cleanup plus evidence refresh. Fixed. |
| source-snapshot senior engineering | PASS AFTER FIXES | None remaining | Requested READY gate and checker-policy template alignment to task-specific policy binding. Fixed. |
| source-snapshot QA/test | PASS AFTER FIXES | None remaining | Requested Chunk 1 proof stay limited to guide snapshot, sufficiency, project policy, effective project policy hash, activation guard, and source/policy invariants. Fixed. |
| source-snapshot security/auth | PASS AFTER FIXES | None remaining | Requested durable source refs never persist query strings and READY require task-level source/policy binding. Fixed. |
| source-snapshot product/ops | PASS AFTER FIXES | None remaining | Requested removal of project-level pre-submit checker wording. Fixed. |
| source-snapshot architecture | PASS AFTER FIXES | None remaining | Requested canonical lineage and removal of old `EffectiveSubmissionArtifactPolicy` source-of-truth naming. Fixed. |
| source-snapshot docs | PASS AFTER FIXES | None remaining | Requested activation/readiness contract alignment and API wording cleanup. Fixed. |
| source-snapshot test delta | PASS AFTER FIXES | None remaining | Confirmed compiler proof moved to Chunk 2 and task runtime migration moved to Chunk 3, then requested migration scope and remaining activation-doc cleanup. Fixed. |

## Valid Findings Addressed

- Added explicit untrusted-source-material rules for project owner docs, URLs, repository docs, examples, and imported documents.
- Added immutable `GuideSourceSnapshot` binding with source snapshot id/hash on downstream report, policy, task binding, effective policy, and checker-bundle records.
- Clarified that ordinary URL query parameters may be temporary approved-adapter fetch inputs only; durable source refs cannot persist query strings, signed URLs, credentials, token-bearing refs, local filesystem paths, or private storage paths.
- Clarified that guide text and imported material cannot grant tool authority, override Workstream rules, or weaken default policy.
- Tightened Chunk 1 proof to require Postgres-backed FastAPI/API tests for guide source snapshots, activation blocking, warning acknowledgement by `admin` or `project_manager`, approval provenance, default weakening, source-ref sanitization, append-only policy rows, and effective project policy hash persistence.
- Added per-chunk verification expectations for async guide analysis, submission creation, post-submit policy split, and revision resubmission real API drill.
- Updated activation docs to require guide source snapshot, passed or acknowledged `GuideSufficiencyReport`, approved `SubmissionArtifactPolicy`, `EffectiveProjectSubmissionArtifactPolicy` hash, post-submit checker policy, review policy, revision policy, and payment policy.
- Updated task readiness docs to require `ApprovedTaskArtifactBinding`, `EffectiveTaskSubmissionArtifactPolicy` hash, and task-level `PreSubmitCheckerPolicy` before workers can claim work.
- Replaced stale runtime wording that implied one project-level pre-submit checker with the canonical lineage: `GuideSourceSnapshot -> ProjectSubmissionArtifactPolicy -> EffectiveProjectSubmissionArtifactPolicy -> ApprovedTaskArtifactBinding -> EffectiveTaskSubmissionArtifactPolicy -> PreSubmitCheckerPolicy`.
- Replaced ambiguous `derivation source: manual | workstream_agent | import_adapter` wording with source-material ingestion method and kept derivation agent fields mandatory.
- Added missing approval provenance fields to the data model example.
- Updated loop state to point at the current internal review evidence instead of saying no evidence exists.
- Added ADR 0011 implementation enforcement contract without claiming the backend already enforces it.
- Assigned UI/demo wording proof to a later frontend/demo chunk before ADR closure.
- Added Chunk 4 schema/persistence proof that pre-submit feedback cannot store review decision values.
- Locked the default pre-submit path to constrained checker specifications and Workstream-compiled deterministic checker bundles, not unrestricted generated checker code.
- Added data model fields for `checker_spec`, `compiler_version`, `compiled_bundle_hash`, and immutable `compiled_bundle`.
- Moved compiler proof obligations to Chunk 2, where checker modules and checker tests are allowed.
- Moved task binding, `EffectiveTaskSubmissionArtifactPolicy`, task-level `PreSubmitCheckerPolicy`, transitional task-field replacement, and submission runtime migration to Chunk 3, where task/checker modules and migrations are allowed.
- Tightened future executable-checker extension requirements to require static validation, generated tests, sandbox policy checks, no network, no shell, no secrets, no database access, and `admin` or `project_manager` approval of the exact locked code hash after those checks pass.
- Corrected the checker framework response wording to match the current `PreSubmitCheckResponse` schema: `status`, `eligible_to_submit`, and `results`, with `pre_submission_checker_failed` treated as the user-facing failure condition rather than a response field.
- Corrected the external review response artifact so CodeRabbit feedback is tracked separately from internal review evidence and does not claim a nonexistent `failure_code` field in pre-submit responses.

## Commands Run

```bash
python3 scripts/check_loop_memory_state.py
python3 scripts/check_markdown_links.py
python3 scripts/check_stale_workstream_wording.py
python3 scripts/workstream_agent_gate.py --base origin/main --head HEAD --format json
python3 scripts/check_internal_review_evidence.py
git diff --check
```

## Remaining Risks

- `WS-POL-001-01` is not approved for backend implementation yet.
- Human review should focus on persisted provenance field names and confirming Chunk 1 remains records/contracts/activation guard only.
