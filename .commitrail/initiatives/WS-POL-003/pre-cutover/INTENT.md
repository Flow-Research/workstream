# Intent: WS-POL-003 - Unified Project Guide Compilation

## Human goal

Compile one immutable Project Guide source snapshot into one coherent,
reviewable setup proposal with one logical, idempotency-keyed model attempt per
setup generation. The result must cover guide sufficiency, submission-artifact
policy, atomic guide requirements, supported project-specific pre-submit and
post-submit checker bindings, human-review/lifecycle dispositions, and visible
capability gaps.

The purpose is to remove repeated guide reads and inconsistent independent
agent conclusions without giving the model policy, authorization, checker, or
approval authority.

## Success state

- One verified guide snapshot and setup generation owns one durable model-attempt
  identity and one provider idempotency key. Retries recover that same attempt;
  they cannot issue a second provider request under a different key.
- A structurally invalid or unsafe provider result consumes and terminally
  blocks that generation. Correction or another genuine evaluation requires a
  new setup generation; transport uncertainty is reconciled under the original
  key and can only reuse an already accepted result.
- The accepted result contains sufficiency, submission-artifact, pre-submit,
  and post-submit proposals together before any Project Manager approval can
  occur. Approval never triggers another guide-reading inference.
- Trusted server validation projects the immutable result into the existing
  canonical policy objects; `ProjectGuideCompilation` does not replace them.
- Platform checks remain mandatory and non-selectable.
- ART-04B1 owns the complete pre-submit catalogue: mandatory platform entries
  plus its closed selectable project-rule namespace. CHECKER/POL owns the
  durable post-submit capability registry/compiler. WS-POL-003 consumes both
  read-only and creates neither a duplicate catalogue nor new ART behavior.
- Unsupported required requirements visibly block activation; optional gaps
  require explicit acknowledgement.
- Agent-derived projections are immutable. Correction creates a new setup
  generation, or a separately proven manual policy that cannot claim unified
  agent provenance.
- Project Managers request/recover and approve bounded results; the fixed
  `workstream.project.setup` service alone performs compilation and service
  projection mutations with fresh transaction-bound authorization.
- No prepared handle, guide bytes, extracted content, credentials, or scratch
  path enters a Celery payload.

## Non-goals

- Dynamic checker discovery, generated code, project-provided plugins, network
  checks before submission, or a second checker registry.
- Replacing human review or changing task, review, revision, contribution,
  compensation, payment, or reputation semantics.
- Replacing `ProjectSetupRun`, `GuideSufficiencyReport`,
  `SubmissionArtifactPolicy`, effective policy, `PreSubmitCheckerPolicy`, or
  `PostSubmitCheckerPolicy`.
- Implementing ART-04B1 through 04B3 inside this initiative.
- Changing ART scratch, storage, provider, binding, or lifecycle behavior. This
  initiative provides one typed checker-service call per phase for later
  artifact-flow integration at ART material boundaries.

## Human decisions already captured

- Prefer one unified inference over three complete guide-reading inferences.
- Keep durable policy lifecycles and approval gates separate.
- Separate approval gates operate on components of the already complete
  immutable result; they do not divide model generation into stages.
- Treat the model as an untrusted proposal generator.
- Preserve async-first execution and fixed-service authorization custody.
- Do not preserve compatibility aliases or dual inference paths in v0.1.
- Keep one authoritative execution entry per checker phase: pre-submit runs
  only inside canonical submission preparation/admission, and post-submit runs
  automatically from successful Submission creation/finalization. Platform,
  project, and individual checkers are never separate caller-selected APIs.
