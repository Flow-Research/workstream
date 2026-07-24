# Chunk Contract: WS-ART-001-PLAN2 - Submission Bundle Reconciliation

Initiative: `WS-ART-001` | Risk: L1 | Status: Planning only

## Goal

Reconcile the remaining artifact initiative with current `main` and lock the
smallest v0.1 path that proves one contributor ZIP is safely inspected in
bounded private scratch, checked under the task's locked Project Guide, admitted
once through the existing immutable `ArtifactStore`, and referenced unchanged
by the resulting Submission and every downstream consumer.

This chunk changes planning and contracts only. It does not activate ART,
AUTH, task, checker, review, contribution, or delivery behavior.

## Allowed Files

- WS-ART-001 intent, discovery, plan, decisions, risks, status, chunk map, and
  remaining unimplemented chunk contracts;
- the WS-ART-001 authorization handoff naming exact registration, hidden
  behavior, activation, fixed-service separation, and stop conditions;
- the canonical artifact-storage specification, shared glossary, and one
  availability-neutral authorization-spec clarification needed to remove stale
  multi-step upload guidance without changing AUTH runtime ownership;
- submission artifact-policy and submission-packet templates needed to replace
  caller hash/manifest and multi-step session guidance;
- ART planning review evidence and PR trust bundle;
- `scripts/test_agent_gates.py` only to replace stale ART status/chunk-map
  assertions with the exact merged/cancelled planning projection, bind new
  successor phases/coverage contracts, and preserve the signed-automation-only
  authority warning instead of treating copied root projections as live state,
  plus focused regression assertions required by an in-scope documentation
  gate repair;
- `scripts/check_stale_authorization_docs.py` only for the narrow technical
  background-service module/path recognition repair required to scan the changed
  contracts without re-admitting deprecated human product-role vocabulary;
- cross-initiative handoff prose that names dependencies without modifying
  another initiative's owned runtime contract;
- exactly one merge intent for this planning chunk.

## Not Allowed

- backend, frontend, migration, workflow, provider, or deployment changes;
- Authorization Service catalogue, evaluator, grant, identity, or activation
  changes;
- Review, Contribution, compensation, reputation, or delivery implementation;
- candidate/quarantine object storage, temporary provider namespaces, physical
  deletion, retention windows, or a second artifact recovery aggregate;
- larger upload, expansion, scratch, entry-count, or duration limits without
  separately reviewed capacity evidence;
- starting any successor automatically.

## Acceptance Criteria

- every Submission version accepts exactly one outer ZIP; its contents are
  governed by the locked Project Guide;
- Workstream recursively walks the normalized directory/file tree represented
  by the outer ZIP, while a ZIP entry inside that tree remains an ordinary file;
  nested archive unpacking is explicitly outside v0.1;
- bounded private scratch is the only pre-admission custody; failed, unsafe,
  unchanged, abandoned, or checker-failing attempts never enter object storage;
- the canonical semantic manifest commits to normalized file/directory paths,
  entry type, and each file's SHA-256 and byte count while excluding packaging,
  timestamps, ownership, compression, and platform permission metadata;
- exact archive equality and manifest equality are compared with the immediate
  prior immutable Submission and both reject before provider I/O;
- all mandatory platform gates and locked project pre-submit checks pass before
  the existing `ArtifactStore` admission path is called;
- passing bytes are written once, independently read back, verified, published
  as `ArtifactContent`, and bound to the Submission through existing ART
  identity, put-attempt, verification-job, receipt, and recovery abstractions;
- the plan creates no candidate store, promotion, retention policy, duplicate
  provider write, `ArtifactOutboxRecoveryAttempt`, or provider delete path;
- process loss before durable admission requires reupload; an ambiguous durable
  put uses existing observation/recovery and never creates a Submission until
  verified content is bindable;
- current conservative configured limits remain unchanged;
- the current `Submission` row remains the immutable version aggregate; a new
  version links through `supersedes_submission_id` and, when responding to
  `needs_revision`, through an exact review relationship owned jointly with
  REV rather than a competing `SubmissionVersion` table;
- reviewer decision values remain exactly `accept`, `needs_revision`, and
  `reject`; reviewer note/findings attach to the exact Submission and contain
  no reviewer-uploaded revision artifact;
- normal reads use indexed latest/current/accepted projections while immutable
  Submission/Review relationships preserve complete history;
- checker materialization and downstream reviewer/delivery streaming resolve
  the exact binding and recompute full SHA-256 and byte count while streaming;
- ART owns identity, integrity, manifests, binding, and byte access; AUTH, REV,
  CON, and delivery consume explicit capabilities through their own reviewed
  contracts and activation sequence;
- the obsolete multi-step upload-session action plan is not reused blindly:
  AUTH first registers one planned contributor action
  `artifact.submission_bundle.prepare` mapped to `submission.create`, ART-04A-C
  then implement one hidden continuous orchestration, and AUTH alone activates
  that action after exact manifest/guard proof; existing fixed service actions
  remain distinct for verification, pending-work scanning, put resolution,
  checker materialization, and binding;
- every implementation successor is PR-sized, names exact allowed/forbidden
  files, and requires a separate signed start.

## Verification

```bash
git diff --check
python3 scripts/check_stale_artifact_contracts.py
python3 scripts/test_agent_gates.py
python3 scripts/check_markdown_links.py
rg -n "candidate storage|seven-day|7 days|ArtifactOutboxRecoveryAttempt|SubmissionVersion table" .agent-loop/initiatives/WS-ART-001-immutable-artifact-storage docs
```

The wording scan may match an explicit rejection in this planning contract or
decision log; it must not find an active design that implements those concepts.

## Required Reviewers

Senior engineering, architecture, QA/test, security/auth, product/ops,
reuse/dedup, CI integrity, test delta, and docs.

## Human Review Focus

- Is one outer ZIP the only contributor submission boundary?
- Can any failed or unchecked payload reach immutable object storage?
- Is scratch clearly ephemeral rather than a second artifact store?
- Does the plan preserve exact bytes across checks, review, acceptance,
  contribution, and delivery without moving ownership into ART?
- Are AUTH activation and cross-initiative handoffs explicit and fail closed?
