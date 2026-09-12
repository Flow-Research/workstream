# POL-05B — Public manager proposal review, approval and manual correction dispatch

- Initiative: `WS-POL-003`
- Durable disposition: `Planned`
- Intended merge outcome: expose the existing complete proposal, pre-submission approval and correction operations with exact Project Manager authority, and dispatch a committed correction through the sole unified setup runtime.

## Intent and current owners

Managers must inspect both pre/post proposals and findings before approving the
pre-submission policy or requesting correction. POL-05A owns those hidden
operations and immutable receipts; AUTH-12F4 supplies current exact-project
human authority. This chunk connects them to FastAPI/OpenAPI. Post-submission
projection/approval remains POL-06, before CP06/CP07 and complete guide activation.

`GuideProposalService` owns read/approval/correction in a caller transaction.
`GuideCompilationService.request_correction` already reserves a successor through
the human request action and owns its transaction. `LiveGuideCompilationCoordinator`
currently always requests automatic admission; it must recognize an already
committed human request rather than synthesize automatic source consent.
`setup_queue` and the continuation scan already own durable dispatch/recovery.

## Bounded change

### Allowed

- PROJECTS proposal API schemas/router, setup response/diagnostic pointer and request composition dependencies;
  `app/api/router.py`; explicit AUTH/CHECKERS/ART composition through public ports.
- Existing proposal service and correction request owner where needed for route
  scoping, transaction ownership and removal of superseded unconfigured paths.
- Existing compilation request/live coordinator, queue and continuation owners
  only to carry committed human correction requests into the same worker.
- Focused PROJECTS API, proposal, runtime and PostgreSQL tests; affected exact
  public-route, action, ownership and semantic-lane inventories.
- Current README, API/operating specifications, roadmap and adopted POL navigation.

### Not allowed

No post-submit approval/projection, checker evaluation, guide activation, CP06,
model/runtime/provider changes, new authorization permissions, migrations unless
an independently demonstrated existing custody constraint requires correction,
second compiler or runtime, compatibility routes, retained-data deletion,
archive-limit changes, frontend or private guide fixtures.

## Design

1. Expose exact compilation-scoped GET review, POST pre-submission approval and
   POST correction. Body target must match project/guide/compilation path;
   mutations use the canonical UUID Idempotency-Key header, mapped into existing
   commands rather than duplicate client body/header keys. Read returns the existing
   complete display-only package and target, never a latest diagnostic substitute.
   Existing setup diagnostics expose an optional finalized compilation ID from
   their existing finalization lookup so clients can discover the exact selector;
   it is a pointer only and does not grant complete proposal access.
2. Compose human admission, identity, exact request context and
   `GuideProposalAuthorizationAdapter` at the HTTP boundary. Reuse the nominal public authority port;
   services must require explicit authority, removing unconfigured preservation
   paths and updating their affected callers/tests. Read and mutations preserve
   root transaction/locked grant custody through response construction/commit.
3. Expose a correction-operation-scoped manual dispatch command. It validates
   project/guide/compilation membership before admitting that operation through
   `GuideCompilationService.request_correction`; the server-owned correction
   identity supplies stable request idempotency (no second dispatch key). Return
   a redacted dispatch response with correction operation, successor setup identity
   and bounded status only; never expose the internal receipt/provider key.
   No HTTP request invokes a model.
   Current PM authority is checked on every dispatch/replay.
4. In the existing request transaction, after attempt reservation, AUTH consume
   and human request insertion, persist `dispatch_pending` / `dispatch` and the
   canonical `celery_task_id`. Then call the existing after-commit dispatcher with
   `claimed_task_id`. This avoids the fresh-queued 60-second suppression without
   weakening recovery predicates. Use existing dispatch/recovery owners;
   broker failure retains retryable intent. The worker executes the existing
   authorized human attempt under current execution-service authority and the
   saved runtime configuration. Under the existing scope/generation locks, branch
   on the immutable request operation linked to the admitted attempt: a human
   `project_manager` request skips automatic request authority/admission, while
   `automatic_source_ready` preserves current request/replay. Missing or duplicate
   request custody and trigger/attempt/scope/predecessor mismatches reject delivery;
   an attempt alone is never sufficient. Automatic source-ready behavior remains intact;
   unknown/invalid terminal provider outcomes never become a fresh attempt.
5. Approval uses canonical ART manifest, CHECKERS catalogues/planner and existing
   output receipt. No second policy compiler, approval chain or finalization edit.
6. HTTP errors conceal authority/selector failures as 404; stale target, conflicting
   operation or blocked approval are 409; storage failure is 503; invalid bodies
   and replay headers are 422. Responses contain bounded messages only.

## Acceptance criteria

- Exact PM can read ready or blocked complete proposals. Foreign scope, service,
  Audit/Operator-only, revoked/inactive identity and mismatched selectors disclose
  no package or source handles. OpenAPI exposes all required public steps.
- Approval of the exact displayed target commits one artifact/effective/pre
  chain with existing audit evidence; invalid selection/configuration, stale
  target and missing warning acknowledgement fail without partial writes.
  Approval makes zero provider calls and never activates the guide/post-policy.
- Replay retains original evidence and output while checking fresh current
  authority. Concurrent approvals remain one chain using existing DB custody.
- Correction preserves predecessor finalization and allocates one successor.
  Manual dispatch enters the same runtime exactly once per reserved attempt;
  duplicate delivery/dispatch, broker failure and crash recovery cannot create
  another provider invocation or bypass current authorization.
- Remove affected obsolete assumptions/tests that claim these routes are hidden;
  preserve required denial, locked lineage, atomicity and immutable evidence tests.

## Risk and review

- Risk class: L1 (public authorization, transactions and async dispatch).
- Required reviewers: architecture/reuse, security, QA/test delta,
  documentation/product operations; CI integrity for affected selection/inventories.
- Human focus: complete inspect-before-approve journey; correction followed by
  explicit manual dispatch; no unintended post-submit activation or second agent.
- Plan review required before product edits. Tests below are planned proof,
  not claims of completed execution.

## Verification

Add real HTTP/ASGI tests with production AUTH composition and PostgreSQL fixture
lineage through existing authorized project/guide creation and finalized proposal
helpers. Seed an exact-project PM grant after normal project creation; the
generic client fixture system-scoped PM is intentionally insufficient. Execute
the valid control before scope/role/revocation substitutions. Trace controls
through fixture guards before negative mutations. Test
HTTP path/body substitution and human-only admission; exact response/error status,
OpenAPI action metadata and replay headers. Exercise both ready/blocked package,
real compiler approval, warning and selected-check rejection, concurrent/revoked
access, rollback, correction admission/delivery, broker recovery and zero-call
approval. Reuse real runtime orchestration with a counting provider stub for
manual delivery and replay rather than call-only route mocks. Real-provider smoke
is not required for unchanged inference; no private documents enter this PR.

Run focused suites, relevant lint/boundary/structural checks, Markdown links and
stale wording; preserve >=90% changed-subsystem coverage and all CI thresholds.
Freeze a clean candidate, run impact-routed internal reviews, repair findings,
push and wait for exact-head hosted CI before reporting readiness.

## Reconciliation

Base: merged PR399 (`d9a66470`). Open PR395 concerns public-field drill findings;
inspect its relevant overlap before final reconciliation. Adopted 05B contract
remains linked; this record makes manual dispatch/current owner wiring explicit.
Next usable boundary after this chunk: POL-06 post-submit policy projection and
approval with its own narrow AUTH gate; CP06 follows guide policy completion.
