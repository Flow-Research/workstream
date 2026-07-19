# Loop State

## Current State

- This authored file is reviewed planning/history context, not canonical live
  post-merge state. Canonical state is the signed schema-v2 output on
  `automation/loop-memory`.
- Active initiatives include independently owned `WS-AUTH-001`, `WS-ART-001`,
  `WS-REV-001`, and `WS-CON-001`. The planning-only `WS-XINT-001` boundary
  reconciliation merged through PR #139 as `5d353b6` and starts no runtime.
- AUTH's owner reconciliation merged through PR #140 as `d541521`; it defines
  fixed-service admission, prepared mutation authority, and activation custody
  without activating ART, REV, or CON feature behavior.
- AUTH-09A merged through PR #132 as `299363a`; its fixed service identity
  foundation is preserved as migration `0023_service_actor_identity`.
- AUTH-09B merged through PR #143 as `053242b`; it adds controlled service
  actor provisioning and leaves service runtime admission plus feature actions
  inactive.
- AUTH-09C merged through PR #146 as `0ffdabf`; signed schema-v2 memory at
  `eeb3dc2` recorded its two administrative reads and stopped.
- PR #141 merged `WS-ART-001-02A3` into `main` as `a10d901` on 2026-07-18.
  PR #151 then merged `WS-ART-001-02B1` as `1b5422f` on 2026-07-19;
  ART-02C1 remains inactive pending signed memory and a separate explicit start.
- AUTH-09D-A merged through PR #148 as `99ae4c9`; signed schema-v2 memory at
  `cf8a3e8` recorded the stopped gate and exact 09D-B successor.
- AUTH-09D-B merged through PR #152 as `93dd392`; signed schema-v2 memory at
  `912a6254` stopped and named the contributor foundation as its exact
  successor.
- PR #119 merged `WS-AUTH-001-05B` as `ad71c7e`.
- PR #120 merged `WS-ART-001-OBJECT-STORAGE-AMENDMENT` as `4408256`.
- PR #122 merged the first automated post-merge memory implementation as
  `fc89fb6`; its schema-v1 cross-initiative next pointer is superseded by the
  schema-v2 initiative-local clean cut.
- Active implementation chunk: `WS-AUTH-001-CONTRIBUTOR-FOUNDATION`, explicitly
  started by the user on 2026-07-19 from trusted `main` at `93dd392`. Current
  exact contract `2a21166d` passed required L1 preimplementation review;
  initial findings are repaired, and exact code SHA `4d1fc507` passed all nine
  required internal tracks. PR publication and external checks are the current
  gate; Backend must still prove 78/90 percent aggregate coverage. It changes no action
  availability, and no service caller becomes executable before AUTH-09E.
- Scope checkpoint: AWS S3 is the only v0.1 production provider; MinIO is
  local/CI S3 protocol proof; LocalStorage is focused development/test; R2 and
  Flow Node are deferred. Product modules receive narrow artifact capabilities,
  and AWS cannot instantiate in production without release-bound live proof.
- Authorization checkpoint: trusted main contains 74 PermissionIds and 65
  ActionIds, with 17 active actions: the two actor-self actions, seven AUTH-08
  administrative actions, AUTH-09B `actor.service.provision`, AUTH-09C
  `actor.profile.read` plus `actor.identity_link.read`, and the three merged
  AUTH-09D-A profile lifecycle actions, and the two AUTH-09D-B identity-link
  lifecycle actions.
  Merged AUTH-09A defines seven fixed artifact
  service identities and eleven exact planned static matrix memberships. ART
  feature chunks supply hidden canonical behavior/resource composition. Merged
  AUTH planning requires availability-neutral ART custody transfer, fixed-service
  admission, prepared mutation authority, and exact AUTH-only activation chunks;
  neither reconciliation PR activates feature behavior.
- Parallel artifact checkpoint: ART-02A1, ART-02A2, ART-02A3, and ART-02B1
  merged through PRs #127, #129, #141, and #151. ART-02B1 adds real MinIO
  protocol proof plus a fail-closed, runtime-ineligible native AWS profile;
  ART-02C1 remains inactive.
- Authorization checkpoint: AUTH-07B through AUTH-09D-B merged through PRs
  #130, #131, #132, #143, #146, #148, and #152. The contributor foundation is
  internally approved at code SHA `4d1fc507`; AUTH-09E remains
  inactive.
- Parallel coverage work: `WS-QUAL-001-01B2` remains paused. Its last official
  whole-app result is `6466/8159` statements (`79.249908%`); no replacement
  evidence exists.
- Parallel initiative: `WS-POL-002-03` merged through PR #90 as `a7aa474`; its
  post-merge memory merged through PR #94 as `b1270d7`. `WS-POL-002-04` remains
  inactive pending the relevant authorization proof and a separate explicit
  start.

## Operating Rule

Workstream engineering chunks move through:

```text
Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Automated Merge Memory -> Stop
```

The merged `WS-POL-001-03` chunk moved task readiness and submission creation
onto the locked project guide-source snapshot, effective project submission
artifact policy, and compiled project `PreSubmitCheckerPolicy` bundle. It did
not implement frontend behavior, payment, reputation, settlement, blockchain
integrations, post-submit policy splitting, or revision resubmission drill
behavior.

The merged `WS-POL-001-08` chunk corrected the project setup orchestration path:
normal guide/source capture starts the pre-submit setup pipeline automatically
through Celery. It did not redesign post-submit policy, review, revision,
payment, reputation, blockchain integrations, frontend behavior, or task
submission runtime.

The merged `WS-POL-001-09` chunk was a corrective hardening chunk for the
project setup runtime boundary. It removed the production fixture adapter and
did not change task, checker, post-submit, review, revision, payment,
reputation, blockchain, frontend, or object-storage behavior.

The merged `WS-POL-001-10` chunk was a corrective hardening chunk for the
pre-submit live API drill. It fixed guide-version conflict mapping,
guide-create source snapshot capture, active-guide checker summary visibility,
contributor self-profile onboarding, and failed pre-submit audit evidence. It did
not change post-submit policy, review, revision, payment, reputation,
blockchain, frontend, or agent-runtime behavior.

## Last Review State

- Last completed initiative: `WS-ENG-001` Codex zero-trust engineering loop bootstrap.
- PR #23 merged into `main` on 2026-06-20.
- PR #24 updated post-merge loop memory on `main`.
- PR #25 added Terminal Benchmark example material under `examples/`.
- PR #26 approved and merged WS-POL-001 planning into `main` on 2026-06-27.
- PR #27 updated WS-POL post-merge memory on `main`.
- PR #28 implemented `WS-POL-001-01` and was merged into `main`.
- PR #61 implemented `WS-POL-001-02` and was merged into `main`.
- PR #63 implemented `WS-POL-001-03` from `codex/ws-pol-001-03-task-locked-context` and was merged into `main` on 2026-07-03.
- Internal review evidence for `WS-POL-001-03` is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-03-internal-review-evidence.md`.
- PR trust bundle for `WS-POL-001-03` is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-03-pr-trust-bundle.md`.
- External review response for `WS-POL-001-03` is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-03-external-review-response.md`.
- `WS-POL-001-04` started on branch `codex/ws-pol-001-04-post-submit-policy` after the user's explicit start signal.
- `WS-POL-001-04` internal reviewer fanout completed with no open sub-agent sessions.
- `WS-POL-001-04` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-04-internal-review-evidence.md`.
- `WS-POL-001-04` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-04-pr-trust-bundle.md`.
- `WS-POL-001-04` external review response is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-04-external-review-response.md`.
- `WS-POL-001-04` merged to `main` before `WS-POL-001-05` started.
- `WS-POL-001-05` started on branch `codex/ws-pol-001-05-revision-resubmission` after the user's explicit start signal.
- `WS-POL-001-05` reviewed implementation SHA: `5019afc57e7c6f5f7488f26a05b11c65a33e9f18`.
- `WS-POL-001-05` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-internal-review-evidence.md`.
- `WS-POL-001-05` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-pr-trust-bundle.md`.
- `WS-POL-001-05` external review response is tracked separately at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-05-external-review-response.md`.
- PR #66 merged into `main` as `b20988ba79626e1edbc03953aba60f54f2fc94ab`.
- `WS-POL-001-06` started on branch `codex/ws-pol-001-06-terminal-benchmark-drill`
  after the user's explicit start signal.
- `WS-POL-001-06` real Terminal Benchmark manual HTTP drill passed against a
  local Terminal Benchmark reference fixture; committed evidence uses placeholder fixture
  paths and local IDs only.
- `WS-POL-001-06` live drill exposed and fixed an OpenAI Agents SDK adapter
  strict-schema issue for the policy derivation result's open `policy_body`.
- `WS-POL-001-06` follow-up cleanup removed stale project-owned payment fields
  and removed construction-state guide checklist fields, preserved server-written activation
  provenance on reads, added fail-closed migration behavior for old
  guide-source snapshots, and aligned then-active docs around a payment-term
  model later superseded by `ContributionPolicyVersion` as the sole award-policy
  authority.
- `WS-POL-001-06` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-internal-review-evidence.md`.
- `WS-POL-001-06` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-06-pr-trust-bundle.md`.
- PR #67 merged into `main` as `3cce92c`.
- `WS-POL-001-07` started on branch `codex/ws-pol-001-07-task-contract-cleanup`
  after the user's explicit start signal.
- PR #68 merged into `main` as `3dc6a95`.
- `WS-POL-001-08` started on branch `codex/ws-pol-001-08-celery-project-setup`
  after the user's explicit correction that project setup must run
  automatically from guide/source capture through Celery.
- `WS-POL-001-08` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-internal-review-evidence.md`.
- `WS-POL-001-08` external review response is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-external-review-response.md`.
- `WS-POL-001-08` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-08-pr-trust-bundle.md`.
- PR #69 merged into `main` as `aea7024`.
- `WS-POL-001-09` started on branch `codex/ws-pol-001-09-openai-agent-sdk-only`
  after the user's explicit correction to remove the production fixture runtime.
- `WS-POL-001-09` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-internal-review-evidence.md`.
- `WS-POL-001-09` external review response is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-external-review-response.md`.
- `WS-POL-001-09` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-09-pr-trust-bundle.md`.
- PR #71 merged into `main` as `8a524de`.
- `WS-POL-001-10` started after the user's explicit start signal for the first
  five pre-submit hardening fixes from the live API drill.
- PR #72 merged into `main` as `1bbde47`.
- `WS-POL-001-11` merged through PR #74 as `5cec0e0`; it added local
  Workstream actor identity and actor profile registries for verified Flow
  actors before the next Terminal Benchmark live API drill.
- `WS-POL-001-11` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-11-internal-review-evidence.md`.
- `WS-POL-001-11` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-11-pr-trust-bundle.md`.
- PR #76 merged into `main` as `46e74de`; it implemented `WS-POL-001-12`
  project setup-run and policy visibility APIs.
- `WS-POL-001-13` started on branch `codex/ws-pol-001-13-task-context-apis`
  after the user's explicit start signal.
- PR #77 merged into `main` as `b567bac`; it implemented `WS-POL-001-13`
  task work-context, submission-requirements, and operator-only locked-context APIs.
- `WS-POL-001-13` internal review evidence is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-internal-review-evidence.md`.
- `WS-POL-001-13` external review response is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-external-review-response.md`.
- `WS-POL-001-13` PR trust bundle is tracked at `.agent-loop/initiatives/WS-POL-001-submission-artifact-policy-foundation/reviews/WS-POL-001-13-pr-trust-bundle.md`.
- PR #79 merged into `main` as `53a57c3`; it implemented `WS-POL-001-14`
  submission finalization and HTTP-visible Terminal Benchmark proof semantics.
- PR #84 merged into `main` as `a3d2a3f`; it implemented `WS-POL-001-16`
  Terminal Benchmark live API drill evidence, privacy scrub, and a professional
  PDF report proving the current lifecycle through HTTP-visible APIs.
- PR #85 merged into `main` as `3fc1a68`; it completed `WS-POL-002-PLAN`
  planning for project-guide-derived post-submit checker setup.
- PR #87 merged into `main` as `ed52c21`; it implemented `WS-POL-002-01`
  Post-Submit Compiler Contract with version-stamped default-checker snapshots,
  canonical policy hashing, compiler-boundary validation, and default-drift
  regression tests.
- PR #90 merged into `main` as `a7aa474` on 2026-07-11; it implemented
  `WS-POL-002-03` server-owned post-submit checker policy approval, correction,
  immutable correction history, and bounded setup visibility APIs.
