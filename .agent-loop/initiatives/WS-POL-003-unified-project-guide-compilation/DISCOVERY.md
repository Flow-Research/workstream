# Discovery: WS-POL-003 - Unified Project Guide Compilation

Baseline refreshed: `origin/main` `99c0aaf04efd36c7ac4af4aeec2e9d810f012305`
on 2026-08-08.

## Current behavior

- `backend/app/interfaces/project_agents.py` exposes separate
  `analyze_guide_sufficiency`, `derive_submission_artifact_policy`, and
  `derive_post_submit_checker_policy` contracts.
- AUTH-12E and AUTH-12F3 are merged transitional implementations of the first
  two separate calls. Their action-specific authorization/projection custody
  remains reusable, but their independent invocation paths are not the final
  orchestration and must become unreachable at the unified cutover.
- `backend/app/adapters/project_agents/openai_agent_sdk.py` implements three
  prompts/model calls behind `ProjectGuideAgentRuntime`.
- `backend/app/modules/projects/sufficiency_mutation_service.py` now performs
  sufficiency execution only as the fixed setup service over ART-verified
  material. The Project Manager route is an asynchronous dispatch/recovery
  request.
- `project_setup.py` still sequences sufficiency,
  submission-policy derivation, approval/compilation continuation, and later
  post-submit derivation.
- `backend/app/modules/checkers/compiler.py` is the current legacy pre-submit
  policy compiler now integrated with ART-04B1 catalogue definitions.
- `backend/app/modules/checkers/catalogue.py` implements the immutable
  `PreSubmissionCheckerCatalogue`, exact `v0.1` definition manifest,
  startup-fixed disabled state, and canonical manifest hash.
- `backend/app/modules/checkers/effective_plan.py` implements the pure
  `EffectivePreSubmissionExecutionPlan` compiler and exact locked lineage,
  rule-instance, configuration, catalogue, and plan hashes. It performs no
  checker execution or durable write.
- `backend/app/modules/checkers/runner.py` registers the current durable
  checker implementations. `check_acceptance_criteria_present` is the only
  current non-default project-selectable post-submit checker.
- The obsolete `POST /tasks/{task_id}/submission-precheck` route and direct
  `POST /submissions/{submission_id}/checker-runs` trigger remain reachable.
  ART PLAN5 superseded 04A4 and moved the standalone precheck clean cut to
  ART-05B. Later AUTH-14/cleanup must constrain ordinary post execution to the
  single typed command and preserve only bounded same-attempt repair.
- `backend/app/modules/projects/service.py` deliberately prevents mutation of
  agent-derived policy bodies; that immutability must be preserved.

## Canonical dependencies

- AUTH-12I: hidden unified compilation request/execute activation after POL-03A.
- AUTH-12B2: setup-ledger-only activation after hidden POL-04A; POL-04B owns the live setup-service cutover.
- AUTH-12F4: stored unified pre-submit component approval after hidden POL-05A; no inference.
- AUTH-12G: deterministic stored post-submit projection/approval after hidden POL-06A; zero model calls.
- AUTH-12H: terminal guide activation after POL-07 and the CON clean cut.
- ART-04B1: merged PR #276. The immutable catalogue is exactly
  `workstream.pre_submission_checkers` `v0.1` with schema
  `pre_submission_checker_catalogue.v1`; the pure effective plan is
  `effective_pre_submission_plan.v1` and binds its manifest hash plus locked
  source/effective/pre-submit policy lineage.
- ART-04B2/04B3: sealed scratch/default execution facts consumed through a
  typed boundary; WS-POL-003 does not change those ART behaviors.
- ART-04B2, ART-04B3, and XINT-06A pre-submit materialization activation are
  merged. ART-04C1 is the next admission-path implementation and may proceed
  independently of unified compilation.
- CHECKER/POL: canonical durable post-submit defaults/selectable rules and one
  typed evaluation service with a complete pre and complete post command.
- Artifact-flow orchestration invokes the pre command once while material is
  sealed in scratch and the post command once after verified storage/binding.
  It does not call individual checkers.

## Existing tests to preserve

- `backend/tests/test_projects.py`: setup generation, agent failure,
  idempotency, policy derivation/approval, correction, Celery, and provenance.
- `backend/tests/test_checkers.py`: pre/post compiler and checker registry.
- `backend/tests/test_checker_catalogue.py`: exact 26-entry ART-04B1 catalogue,
  availability, immutable manifest, effective-plan lineage, policy coverage,
  default weakening, and stale/invalid plan proof.
- `backend/tests/test_authorization.py`: action/catalogue/PREP/fixed-service
  isolation.
- `backend/tests/test_tasks.py`: task-locked guide and policy context.
- `backend/tests/test_alembic.py`: migration topology and round trip.
- `backend/tests/test_guide_bindings.py`: ART-verified guide material custody.

## Confirmed risks and gaps

- A manually edited agent projection would invalidate unified result
  provenance. Agent projections must be immutable.
- Unified fixed-service execution needs explicit fresh PREP custody for
  each protected durable boundary; no synthetic human context is acceptable.
- Free-text model output can echo secrets, raw guide excerpts, paths, URLs, or
  prompt injection. Evidence references require a closed structured grammar
  and all persisted text requires bounded sanitization.
- ART-04B1 is merged but intentionally performs no checker execution or durable
  write. WS-POL-003 must consume its exact immutable manifest/effective-plan
  contracts rather than creating an interim registry or assuming 04B2/04B3.
- A post-submit proposal produced early becomes stale if its compilation,
  artifact-policy projection, pre-submit proposal, catalogue snapshot, or
  setup generation changes.
- Representative task material is optional bounded context. Guide setup must
  not depend on tasks already existing.
- The new unified proposal validator must reject platform-default repetition;
  POL-01 does not change historical post-submit compiler behavior.
- A catalogue is not an execution API. The checker service must expose exactly
  one typed call per phase and accept no caller-selected checker names.

## Remaining unknowns after POL-01 contract repair

- POL-01 freezes evidence-reference and safe-text names/limits in its active
  executable contract; implementation must prove them before later chunks.
- Exact AUTH action/resource binding for creation of the compilation record;
  use narrow XINT/AUTH compilation request+execute actions for the parent while
  preserving separate 12E/12F/12G projection actions.
- Whether separately manual policies remain supported after clean cut. If so,
  they require independent provenance and cannot reuse unified proposals.
