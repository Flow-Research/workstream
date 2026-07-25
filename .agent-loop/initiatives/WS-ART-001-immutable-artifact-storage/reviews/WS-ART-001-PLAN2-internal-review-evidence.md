# Internal Review Evidence: WS-ART-001-PLAN2

Reviewed code SHA: `25bae9792208697366bd828230d8f321d819586d`

Reviewed against trusted main: `f3ece23e0f128258947137764b39b7d59dd7b2a8`

Reviewed at: `2026-07-25T09:10:36Z`

Reviewer run IDs: `art_plan2_ext_senior`, `art_plan2_amend_arch`,
`art_plan2_ext_qa`, `art_plan2_amend_security`, `art_plan2_ext_product`,
`art_plan2_amend_docs`, `art_plan2_final_reuse`, `art_plan2_final_ci`,
`art_plan2_final_test_delta`

## Candidate

Planning-only reconciliation after signed cancellation of `WS-ART-001-03`.
No backend, frontend, migration, workflow, provider, or deployment behavior is
implemented or activated.

## Deterministic Evidence

- `git diff --check` — PASS
- `python3 scripts/check_stale_artifact_contracts.py` — PASS at
  `artifact_store_cutover`
- `python3 scripts/check_stale_authorization_docs.py` — PASS
- `python3 scripts/check_markdown_links.py` — PASS
- `python3 scripts/update_post_merge_memory.py validate-merge-intent
  --base-ref origin/main` — PASS
- `python3 scripts/test_agent_gates.py` — PASS, 100 tests
- targeted stale wording scan — only explicit rejected/legacy/unavailable
  references remain

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | The only final finding was this expected evidence refresh; admission, executable, and reauthorization contracts are maintainable and operationally bounded. |
| architecture | PASS | none | Preserved ART/AUTH/TASK/REV ownership, reused existing scratch/admission/recovery, and resolved latest-main review-history integration. |
| QA/test | PASS AFTER FIXES | none | Closed executable-template coverage and proved lifecycle, authorization crossed states, concurrency, and governance gates. |
| security/auth | PASS | none | Preserved prepared-capability ordering, fixed-service separation, concealment, and ready/consumed/stale integrity fencing. |
| product/ops | PASS | none | Preserved one-ZIP contributor flow, reviewer decision vocabulary, and zero downstream effect before immutable Submission consumption. |
| reuse/dedup | PASS | none | Reused `ArtifactScratchManager`, `PreparedArtifact`, `CommittedArtifactSource`, and existing admission/put/verification/recovery paths. |
| CI integrity | PASS AFTER FIXES | none | Canonical headings/merge intent parse; stale-auth scanner remains fail-closed; cumulative 90 percent and repository 78 percent gates remain enforced. |
| test delta | PASS | none | No removed/skipped tests or weakened assertions; 100 agent-gate tests pass. |
| docs | PASS AFTER FIXES | none | Reconciled storage/auth specs and templates, including canonical executable-intent semantics in the submission packet. |

## Material Repairs

- removed candidate storage, retention, promotion, duplicate provider writes,
  physical deletion, and a second recovery aggregate;
- locked one outer ZIP, safe outer-tree inspection, opaque nested archives,
  exact archive identity, and canonical semantic-manifest identity;
- kept failed/unchecked bytes only in bounded process-local scratch;
- split guide cutover into 03A/03B/03C and submission work into
  04A/04B/04C/05;
- retired the future multi-step session design behind an exact AUTH-owned
  registration/activation handoff;
- preserved existing immutable `Submission` as the version aggregate and REV's
  decision/note ownership;
- required integrity recomputation for checker, reviewer, and delivery streams;
- defined verified-but-unbound admissions as capacity-charged
  `ready -> consumed|stale` records with no expiry, deletion, release, retention
  worker, or downstream product effect before atomic consumption;
- included normalized regular-file executable intent in semantic identity while
  excluding arbitrary permission preservation and execution authority;
- required fresh transaction-local AUTH capabilities immediately before durable
  put intent and again during atomic Submission/admission consumption;
- corrected fixed-service contracts to use canonical phase-specific ActionIds,
  with shared `artifact.binding.create` and
  `artifact.checker_input.materialize` named only as PermissionIds;
- strengthened the governance regression to require exact no-expiry, no-release,
  no-deletion, no-cleanup, and no-retention-process admission clauses;
- corrected the materializer regression assertion to inspect its owning 04B
  contract rather than the adjacent 04A contract;
- rebased onto trusted main `f3ece23e` and preserved AUTH-10C, AUTH-002, and
  PLAN2 review history.
- recorded the final amendment review outcome in the canonical review log.

## Accepted Risks

- Current AUTH catalogue/gate rows for upload-session actions remain as exact
  trusted-main planned/unavailable discovery state until the separately reviewed
  AUTH registration contract retires them. They have no route or activation and
  block ART-04A until reconciled.
- Process loss before durable artifact intent requires contributor reupload in
  v0.1; no temporary provider custody is introduced to mask that tradeoff.

Valid findings addressed: yes

Open sub-agent sessions: none
