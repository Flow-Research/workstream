# Internal Review Evidence: WS-ART-001-PLAN2

Reviewed code SHA: `afb883dd4e8ab52fad3d7301b5e865d3a25885a7`

Reviewed against trusted main: `bcf1292e1a591e3e84bf8ee212ee7191d80741fa`

Reviewed at: `2026-07-24T17:35:13Z`

Reviewer run IDs: `art_plan2_ext_senior`, `art_plan2_ext_arch`,
`art_plan2_ext_qa`, `art_plan2_ext_security`, `art_plan2_ext_product`,
`art_plan2_ext_docs`, `art_plan2_ext_reuse`, `art_plan2_ext_ci`,
`art_plan2_ext_test_delta`

## Candidate

Planning-only reconciliation after signed cancellation of `WS-ART-001-03`.
No backend, frontend, migration, workflow, provider, or deployment behavior is
implemented or activated.

## Deterministic Evidence

- `git diff --check` — PASS
- `python3 scripts/check_stale_artifact_contracts.py` — PASS at
  `artifact_store_cutover`
- `python3 scripts/check_markdown_links.py` — PASS
- `python3 scripts/test_agent_gates.py` — PASS, 100 tests
- targeted stale wording scan — only explicit rejected/legacy/unavailable
  references remain

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| senior engineering | PASS AFTER FIXES | none | Reconciled status, state vocabulary, outage behavior, route ownership, and evidence accuracy. |
| architecture | PASS AFTER FIXES | none | Removed duplicate session/candidate paths, reused existing scratch/admission/recovery, and separated generic attempt from legacy item state. |
| QA/test | PASS AFTER FIXES | none | Proved exact verification commands, 78/90 percent gates, nested-archive closure, process-loss behavior, and governance parsing. |
| security/auth | PASS AFTER FIXES | none | Kept 04A non-routable, removed the unmapped GET, preserved AUTH activation custody, and closed canonical-path collisions. |
| product/ops | PASS AFTER FIXES | none | Corrected reviewer/revision semantics and separated pre-intent reupload from durable ART/checker recovery. |
| reuse/dedup | PASS | none | Reused `ArtifactScratchManager`, `PreparedArtifact`, `CommittedArtifactSource`, and existing admission/put/verification/recovery paths. |
| CI integrity | PASS AFTER FIXES | none | Canonical headings/merge intent parse; stale-auth scanner remains fail-closed; cumulative 90 percent and repository 78 percent gates remain enforced. |
| test delta | PASS | none | No removed/skipped tests or weakened assertions; 100 agent-gate tests pass. |
| docs | PASS AFTER FIXES | none | Reconciled storage/auth specs and all live submission/manifest templates. |

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
- required integrity recomputation for checker, reviewer, and delivery streams.

## Accepted Risks

- Current AUTH catalogue/gate rows for upload-session actions remain as exact
  trusted-main planned/unavailable discovery state until the separately reviewed
  AUTH registration contract retires them. They have no route or activation and
  block ART-04A until reconciled.
- Process loss before durable artifact intent requires contributor reupload in
  v0.1; no temporary provider custody is introduced to mask that tradeoff.

Valid findings addressed: yes

Open sub-agent sessions: none
