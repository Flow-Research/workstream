# WS-EXEC-001-03 — Deployment and public microVM journey

- Initiative: WS-EXEC-001
- Durable disposition: Complete
- Intended merge outcome: deploy the typed intake/execution capabilities coherently and prove public upload through durable governed outcome on an isolated self-hosted Smol node.

## Intent

Complete the user's authorized end-to-end goal. Boundaries 1 and 2 provide node
lifecycle and ART integration; neither synthetic node grants nor isolated ART
callbacks establish the public contributor journey. Preparation must overlap the
same authorized upload, clean up under failure, and preserve exact immutable
submission and ContributionRecord evidence through durable workers.

## Current owners and concrete gap

Merged main remains `733c752f7c1ecbb74615d42b747dfbda8ff72df5` (verified remotely).
The stacked intake candidate is `2c9c6685fd3de12d2976504fe0f9e0b1bc4bf3e5`.
Its API and POST composition require the new typed intake configuration, while
hosted Compose/preflight and the opt-in public journey probe still construct a
Docker-only node. The existing public probe already exercises public project/guide
setup, upload feedback, immutable Submission, prefork Celery/Beat, known pre-effect routing
retry, true-policy review routing and false-policy shared acceptance/awards. Extend
that probe and deployment owners; do not create another lifecycle or business writer.

## Bounded change

### Allowed files and responsibilities

- `deploy/hosted/compose.yml`, `release.env.example`, `preflight.py`, `compose.py` and their
  existing `scripts/test_hosted_release_config.py` tests: require pinned intake
  identities and mount its private Unix socket into API/Celery processes;
  retain existing artifact-store, secrets and project execution boundaries.
- `external_checkers/deploy/`, `external_checkers/README.md`: concrete Smol
  provisioning/startup/recovery instructions and exact source/cache custody.
- `experiments/pilot04_external_checker_runtime/run_public_journey_probe.py`,
  `guide_runtime.py`, `guide_inputs.py`, its existing shared probe helpers,
  Dockerfile/checker proof fixture and README:
  accept a provisioned node/config rather than inventing a hard-coded Docker
  runtime; verify both typed health identities and use the existing public flow.
  Add only focused proof helpers needed for upload overlap/cancel and exact
  runtime/cleanup observations.
- `.github/workflows/release-images.yml` and `scripts/test_public_smol_proof.py`:
  execute the fault-control safety regressions in required CI and trigger on their
  proof owners. Preserve all existing checks, pins and permissions.
- Focused existing release/probe tests, docs describing deployment prerequisites,
  roadmap, initiative records and index reconciliation.
- Disposable EC2 resources in a uniquely owned directory/unit/container/database/
  port namespace; no shared service restart, prune, volume deletion or edits to
  `/etc/workstream/` or the other agent's protected services.

### Prohibited changes

No policy, authorization, database schema, review/acceptance/award semantics or
artifact provider changes. No product row injection to manufacture submissions,
checks or acceptance. Existing documented infrastructure identity/bootstrap
fixtures are permitted and must be labeled. No host ZIP/default fallback,
checker network escape, ad hoc adapter factory, model gateway replacement or
claims of live external model invocation from recorded guide inference. Defects
in boundary 2 return to that owner/PR for a focused regression and review.

## Plan

1. Reconcile boundary 2 repairs before using its candidate for final proof.
   Preserve its exact source/image/binary custody; build the project proof image
   from the same tree and provision its canonical cache entry.
2. Extend hosted composition with the three required intake settings and private
   socket mount. Preflight validates deployment-owned socket metadata, pinned
   image/config and Smol identity without widening credentials or permissions.
   Project Docker/runsc and Smol intake may be separate nodes; the live drill uses
   one Smol node for both, with one execution slot to expose ordering deadlocks.
3. Replace the public probe's hard-coded Docker construction with explicit
   provisioned-node input and typed capability readiness. Retain its existing
   settings parity, public guide/policy flow, immutable evidence and durable
   workers. Failure injection targets only the probe's exact owned resources.
4. Run on EC2 with isolated real PostgreSQL, MinIO (S3 protocol) and Redis plus
   API, Celery prefork and Beat. Use documented local Flow verifier fixtures and
   recorded guide inference; label these limits. This proves the self-hosted
   execution path, not native AWS S3 activation or production Flow certification.
5. Record public response IDs, ZIP and manifest hashes, selected PRE/POST attempt
   IDs, exact locked policy hashes, durable outbox retries and final facts. Read
   durable rows only to independently verify the public outcomes; create business
   state through existing public APIs/authorized durable owners.
6. Test cancellation/deadline and controller death with a separate in-flight
   attempt; confirm cleanup and recovery before a fresh request. Do not retry an
   unknown guest execution in-session or reuse a dirty VM. Preserve foreign
   resource controls.
7. Extend `RecordedGuideRuntime` explicitly for zero, one and two project PRE
   requirements. Select the recorded project variant from its exact public guide
   source, not by mutating approved policy rows. Preserve the existing one-image
   capability registration and one-binding journey. The two-binding compilation
   assigns distinct requirement IDs to the same registered PRE image; its check
   specification and fixture image distinguish those IDs. Public compilation,
   manager approvals and activation lock the resulting canonical order. The
   zero-binding variant compiles no project PRE requirement and retains default
   intake plus its required POST requirement. Extend the guide document/examples
   assertions per variant rather than disabling evidence checks.
8. Add named proof helpers `_assert_default_only_pre`,
   `_assert_ordered_pre_and_stop`, and `_assert_no_submission_after_intake_failure`.
   Read selected PRE evidence to verify zero/two binding counts and canonical
   order; a first-binding rejection marker makes the first fail while the second
   would pass if incorrectly invoked. Assert there is no second member/execution
   and no admission/Submission. A passing two-binding fixture must show both
   exact request identities after confirmed intake cleanup.

## Distinct failure and retry trials

Do not describe the existing `_wait_known_retry` as a runtime outage: it proves
known pre-effect completion-routing refusal while the lifecycle is non-live,
followed by the authorized live transition. Retain that proof separately.

- `_assert_prepare_retry_bound`: use the owned Smol executable shim/control
  launch injection before any guest input to fail known VM create/start launch
  attempts. The node retries only after exact lease cleanup, at most three
  attempts with the existing 100/200 ms backoff charged to the same deadline.
  Record launch counts, original deadline and absence of residual disks/cgroups;
  exhausted failure creates no selected completion, admission or Submission.
- `_assert_public_intake_recovery`: stop only the owned intake node before an
  authenticated upload, or inject a known project PRE execution outage after
  reservation. Assert public 503, exact selected terminal infrastructure code
  when execution is known (otherwise unresolved lease), and no admission or
  Submission. Same-key replay must preserve the owner's existing recovery
  contract; it must not silently rerun a terminal failure. Restart the node and
  use a fresh authorized request/key to repeat upload and checks successfully.
- `_assert_post_runtime_failure`: keep intake available and inject an outage in
  the owned project execution node after immutable Submission creation. Await
  the terminal `CheckerRun.infrastructure_failed` directly, not `_complete_post`
  (which requires completed work and a completion event). Assert no fabricated
  completion event, acceptance or contribution. Restore the node, then invoke
  the existing public Operator discovery/retry routes backed by `checker_retry.py`,
  with fresh authorization and a new request key; assert its exact next evaluation
  generation, durable dispatch, real worker success and single governed result.
  Discovery confirmed the public routes already exist in `checkers/router.py`;
  use that entry instead of calling the hidden owner directly. No new route is needed.
- `_assert_unknown_execution_cleanup`: kill only the owned controller after
  guest invocation begins, observe connection loss/unresolved status and no
  in-session retry. Verify guardian cleanup and startup reconciliation before a
  fresh request. Retain exact attempt/lease IDs and assert no duplicate business
  facts. Controller recovery must not reset the original attempt deadline.

Each trial uses uniquely owned unit/socket/cache/VM/DB resources. Evidence records
whether entry was public API, durable worker, or the existing public Operator
retry route; no direct SQL writes manufacture lifecycle outcomes.

## Acceptance criteria

- API and Celery resolve identical required intake identity/socket settings;
  missing/wrong runtime or image fails before unsafe processing. Release tests
  reject missing settings/mounts and preserve unrelated secrets/provider checks.
- A deliberately delayed authenticated ZIP request observes ready intake before
  upload ends; unauthorized upload observes no new lease. Disconnect releases
  exact owned VM/disk/cgroup within the original bound and creates no Submission.
- Invalid ZIP/default/project work returns actionable bounded intake feedback and
  creates no Submission; infrastructure outage is distinct and recoverable.
- Default-only and two canonically ordered project PRE bindings run on a one-slot
  node. Intake cleanup precedes the first project connection; failure stops the
  remaining bindings. A subsequent fresh upload repeats the whole authorized flow.
- A valid public request creates one immutable Submission with exact ZIP/manifest
  and locked-policy lineage, then real Celery performs POST through guest intake
  and the selected external execution adapter. No host ZIP/default execution.
- `human_review_required=true` retains review-pending routing without a fabricated
  Review/acceptance/contribution. `false` reaches the existing shared authorized
  FinalAcceptance and exact submitter ContributionRecord and conditional awards
  atomically, with no reviewer contribution. Duplicate delivery creates no new facts.
- Known infrastructure failure/retry, caller cancellation, deadline and controller
  restart preserve durable outcome distinctions and settle only owned resources.
- Final proof binds a clean source candidate, packaged image and runtime binaries;
  full required suite/checks and focused internal reviews pass before readiness.

## Risk and review routing

Risk L1. Required plan review before implementation, then architecture/reuse,
security, QA/test-delta, product/operations, documentation and CI integrity for
release/proof gates. Human focus: deployment authority, one-slot ordering,
public-to-durable custody, retry safety and exact contribution evidence.

## Evidence

The isolated EC2 public journey passes on real KVM, PostgreSQL, MinIO and Redis,
with the API, Celery prefork worker and Beat. It exercises original public guide
setup/approvals, authorized upload overlap and cancellation, zero/two project PRE
bindings, first-failure stop, immutable Submission, revision, launch retry/exhaustion,
controller death/epoch recovery and durable POST failure followed by public Operator
retry generation 2. Every recovery checks owned cleanup and preserved foreign
controls. Human review remains pending with no final facts; automatic acceptance
creates one FinalAcceptance, one submitter ContributionRecord and one 7 PTS award,
with no Review. Duplicate delivery and late authority revocation preserve those facts.
Database and MinIO cleanup complete. Source/image/binary identities and exact run
receipts remain in the PR evidence; no production deployment is inferred.

The public two-binding trial exposed ART's sequential grant-layout defect; its
repair and discriminating PRE/POST regressions belong to boundary 2. Review also
strengthened the proof itself: independently supplied node/binary custody, exact
controller kill and disk cleanup, explicit idle-node checks under optimized Python,
CI ownership of safety tests, one-slot enforcement, fixture-derived artifact hashes,
request-correlated execution counts, cancellation resource readback and per-machine
original retry leases. Retry wall-clock projections permit only the observed
one-millisecond flooring difference while remaining lifetimes must shrink; the
Rust operation retains one monotonic deadline. The timeout trial requires `deadline_exceeded` at the original
lease expiry, with no in-session retry. Required hosted checks and reviewer freshness
are reported against the final PR candidate, not stored as durable workflow state.

The 33 hosted configuration tests and focused negative fault-control tests preserve
existing release gates. The drill intentionally uses recorded guide inference and
a local Flow verifier fixture; MinIO establishes the S3 protocol, not native AWS
activation. Intended hosted deployment and actual external-model invocation remain
separate. No shared EC2 service or product business owner was changed.
