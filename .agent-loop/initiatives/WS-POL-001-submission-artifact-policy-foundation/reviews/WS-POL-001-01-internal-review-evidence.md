# Internal Review Evidence: WS-POL-001-01

## Chunk

WS-POL-001-01

open sub-agent sessions: none

valid findings addressed: yes

## Reviewed Revision

Reviewed code SHA: 0498bbe66468891c8285bb22b1365fee699c2f05

Reviewed at: 2026-06-23T16:39:43Z

Reviewer run IDs: 019ef3df-a4ae-71f0-b50c-dbd99e65af6c, 019ef3e0-cc78-7583-abd8-826f77b6d435, 019ef3e2-d1fc-7642-b079-561bf61b3d07, 019ef3e5-1e10-78f2-b272-f06200c50334, 019ef3e7-6f3d-7730-a2fd-adc55e496811, 019ef3ea-b44c-7741-9ced-b05bb6a5e5d2, 019ef432-a806-75c1-96ac-11c93eea2f9c, 019ef45d-540a-71e1-9531-19277d5450ed, 019ef45f-a5fa-7721-b9ae-aa39b1f6778e, 019ef462-b086-7923-a03e-78c298316f73, 019ef466-2433-7bf3-9335-069cfa5b5838, 019ef46a-171d-7b42-9795-773132754ff0, 019ef46e-dcea-7423-aa46-47a27b098c85, 019ef51b-8491-7192-a868-f2cbc1c56079, 019ef51d-cc5d-7d40-b5e6-0966c546e465, 019ef520-eea1-71c0-919a-63d24728ff32, 019ef523-f173-7e71-8685-902518610fda, 019ef52a-1da8-7df2-9428-c96b1b0cc164

After reviewed SHA `0498bbe66468891c8285bb22b1365fee699c2f05`, only review evidence artifacts changed.

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

## Valid Findings Addressed

- Added explicit untrusted-source-material rules for project owner docs, URLs, repository docs, examples, and imported documents.
- Added source-ref sanitization requirements for signed URLs, query-bearing refs, credential-bearing refs, and local filesystem paths.
- Clarified that guide text and imported material cannot grant tool authority, override Workstream rules, or weaken default policy.
- Tightened Chunk 1 proof to require Postgres-backed FastAPI/API tests for activation blocking, warning acknowledgement by `admin` or `project_manager`, approval provenance, default weakening, source-ref sanitization, and pre-submit policy locking.
- Added per-chunk verification expectations for async guide analysis, submission creation, post-submit policy split, and revision resubmission real API drill.
- Updated activation docs to require passed or acknowledged `GuideSufficiencyReport`, approved `SubmissionArtifactPolicy`, persisted `EffectiveSubmissionArtifactPolicy` hash, generated `PreSubmitCheckerPolicy`, post-submit checker policy, review policy, revision policy, and payment policy.
- Replaced stale runtime wording that implied recomputing/generating pre-submit policy at submission time with loading the locked effective policy hash and locked `PreSubmitCheckerPolicy` snapshot/hash.
- Replaced ambiguous `derivation source: manual | workstream_agent | import_adapter` wording with source-material ingestion method and kept derivation agent fields mandatory.
- Added missing approval provenance fields to the data model example.
- Updated loop state to point at the current internal review evidence instead of saying no evidence exists.
- Added ADR 0011 implementation enforcement contract without claiming the backend already enforces it.
- Assigned UI/demo wording proof to a later frontend/demo chunk before ADR closure.
- Added Chunk 4 schema/persistence proof that pre-submit feedback cannot store review decision values.
- Locked the default pre-submit path to constrained checker specifications and Workstream-compiled deterministic checker bundles, not unrestricted generated checker code.
- Added data model fields for `checker_spec`, `compiler_version`, `compiled_bundle_hash`, and immutable `compiled_bundle`.
- Added proof obligations for primitive allowlisting, unknown primitive rejection, canonical compiled bundle hashing, hash binding to `effective_submission_artifact_policy_hash`, immutable compiled bundle behavior, and absence of executable code fields by default.
- Tightened future executable-checker extension requirements to require static validation, generated tests, sandbox policy checks, no network, no shell, no secrets, no database access, and `admin` or `project_manager` approval of the exact locked code hash after those checks pass.

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
