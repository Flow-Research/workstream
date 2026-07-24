# Internal Review Evidence: WS-ART-001-PLAN2

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

| Track | Result | Resolved findings |
|---|---|---|
| Senior engineering | PASS after repair | Reconciled status/map history, completed 03A-C contracts, made 04A-C internal composition executable, restored isolated coverage/e2e proof. |
| Architecture | PASS after repair | Removed duplicate session/candidate paths, reused existing scratch/admission/recovery, and made cross-subsystem ownership explicit. |
| QA/test | PASS after repair | Added exact verification commands, 78/90 percent gates, nested-archive closure, process-loss behavior, and migration/history proof. |
| Security/auth | PASS after repair | Added exact AUTH handoff, fixed-service separation, pre-submit evidence privacy, and fail-closed scratch/provider boundaries. |
| Product/ops | PASS after repair | Corrected merged lineage, reviewer note/findings semantics, and Submission/revision/downstream ownership. |
| Reuse/dedup | PASS after repair | Reused `ArtifactScratchManager`, `PreparedArtifact`, `CommittedArtifactSource`, and existing admission/put/verification/recovery paths. |
| CI integrity | PASS | No workflow weakening; cumulative scoped 90 percent and repository 78 percent contracts remain enforced. |
| Test delta | PASS after repair | Replaced stale authored-state assertions without treating root projections as canonical; new phases and e2e ownership remain guarded. |
| Docs | PASS after repair | Reconciled storage/auth specs, glossary, artifact-policy template, and submission-packet template. |

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
