# ARCH-02I-A — Hidden structured pre-submit feedback

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: the existing authorized submission-bundle preparation
  route returns the retained canonical path-free pre-submit findings for a
  blocked upload while remaining absent from OpenAPI and creating no Submission.

## Intent

Give a contributor actionable feedback for the exact ZIP they just uploaded
without activating public Submission creation or depending on unfinished
post-submit remediation. The first contributor milestone requires a failed
pre-submit check to explain what the contributor can correct. ART and CHECKERS
already retain and validate those bounded facts, but the mounted preparation
route currently discards them and returns only `pre_submission_checker_failed`.

This is an independent foundation for the later ARCH-02I cutover. It does not
make the first contributor journey publicly usable: the preparation route stays
out of OpenAPI, production evaluation handlers remain unregistered, and public
Submission creation and checker-remediation replacement remain unavailable.

## Current behavior

- `PreparedSubmissionBundlePreparationCommand.prepare()` in
  `backend/app/modules/artifacts/submission_admission.py` receives a validated
  `PreSubmitEvidencePersistenceResult`. When `execution.eligible` is false, it
  raises `SubmissionBundlePreparationRejected("pre_submission_checker_failed")`
  and discards the canonical result facts from the response path.
- `PreSubmissionExecutionResult.bounded_facts()` and
  `PreSubmissionExecutionFacts` in the CHECKERS API already provide the ordered,
  closed, path-free result projection. ART persists the same result set before
  returning the rejection.
- `prepare_submission_bundle()` in
  `backend/app/api/routes/artifact_submissions.py` maps every ordinary rejection
  to a plain HTTP error. The route is mounted and authorized, so changing its
  same-request response is actual behavior even though `include_in_schema=False`
  keeps it out of OpenAPI.
- Contributor and manager Submission and CheckerRun history reads already exist
  through TASK/CHECKERS owner ports. This change does not add a parallel outcome
  projection.

## Bounded change

### Allowed

- Add one typed `pre_submission_checker_failed` rejection carrier to
  `backend/app/modules/artifacts/api/submission_preparation.py`. It carries the
  existing CHECKERS-owned `PreSubmissionExecutionFacts`; it does not define a
  second checker-result contract.
- Raise that typed rejection from
  `backend/app/modules/artifacts/submission_admission.py` only after the canonical
  ineligible execution and immutable evidence have completed.
- In `backend/app/api/routes/artifact_submissions.py`, return the canonical API
  error envelope with `status`, `eligible_to_submit`, and ordered `results`
  projected from the existing bounded facts. Preserve the canonical result
  fields, including permitted actionable failure/message codes and bounded
  integer metadata. Do not load or reconstruct raw archive findings.
- Add focused behavior proof in
  `backend/tests/test_submission_bundle_preparation_recovery.py` and
  `backend/tests/test_submission_bundle_admission.py`; use an existing broader
  preparation test only if needed to prove no Submission/admission/task mutation.
- Update only current claims that say the mounted hidden route returns the code
  alone: `docs/architecture_checker_framework.md`,
  `docs/architecture_data_model.md`, `docs/architecture_lockdown.md`,
  `docs/decision_0011_submission_artifact_policy_drives_pre_submit.md`,
  `docs/glossary.md`, `docs/operations_project_operating_manual.md`,
  `docs/template_checker_policy.md`,
  `docs/template_submission_artifact_policy.md`,
  `docs/template_submission_packet.md`, and the affected capability statement in
  `docs/roadmap_status.md`. Historical early chunk specifications remain
  unchanged. The lead owns final shared roadmap/navigation reconciliation.
- This change record. Update the initiative overview or current plan only if
  final reconciliation shows that their usable boundary materially changes.

### Not allowed

- No new route, OpenAPI exposure, public Submission creation, automatic
  admission consumption, remediation replacement, human-review revision, task
  audit publication, worker/handler registration, runtime activation, external
  checker implementation, migration, persisted field, provider coordinate,
  scratch coordinate, raw path/name, checker configuration, raw message, review
  decision, compatibility response, or alternate result schema.
- Do not change pre-submit execution, policy compilation, pass eligibility,
  durable evidence, admission, post-submit CHECKERS outcomes, TASK lifecycle,
  authorization, or error classification outside the exact blocked-feedback
  response.
- Do not expose `accept`, `needs_revision`, or `reject` as pre-submit values.
  Do not suppress permitted actionable findings merely because their canonical
  codes or bounded counts describe a contributor-correctable failure.

## Design and decisions

CHECKERS remains the result owner. ART carries the already validated
`PreSubmissionExecutionFacts` across its existing public preparation API, and
the HTTP adapter serializes that exact bounded projection. A new parallel
Pydantic result model or a route-local allowlist would create two contracts and
could silently drop future canonical findings, so neither is introduced.

The error detail adds only the envelope required by the accepted intake
contract: `status="failed"`, `eligible_to_submit=false`, and the canonical
ordered entries. `PreSubmissionExecutionFacts` excludes ART custody. Its entry
facts contain stable catalogue/policy identity, public checker name, closed
status/severity, actionable failure and message codes, and non-negative bounded
count metadata; they contain no archive paths, filenames, bytes, provider
references, scratch state, credentials, or free-form checker output. Existing
validation remains the authority for that boundary rather than a second HTTP
filter.

Other rejection classes retain their current status and response. In
particular, unresolved execution/evidence custody remains retryable
infrastructure failure and must never be rendered as contributor-correctable
feedback. Context conflicts remain conflicts, and unavailable or denied
resources remain concealed.

## Acceptance criteria

- [ ] An authorized blocked preparation returns HTTP 422 with canonical error
      code `pre_submission_checker_failed` and details containing exactly
      `status="failed"`, `eligible_to_submit=false`, and the ordered canonical
      bounded results for that execution.
- [ ] Feedback preserves public checker names, closed result status/severity,
      actionable failure/message codes, and canonical bounded count metadata.
      It contains no paths, filenames, raw bytes/messages, provider/scratch
      coordinates, credentials, checker configuration, review-decision field,
      or review-decision value.
- [ ] The blocked attempt retains immutable pre-submit evidence but creates no
      ready admission, Submission, submission version, task transition, or
      submission-created event. Exact replay returns the same canonical
      feedback rather than executing another checker or minting a pass.
- [ ] Context conflict, unavailable authority, and unresolved/corrupt execution
      custody preserve their distinct existing 409/404/503 behavior and expose
      no structured checker results.
- [ ] The preparation route remains absent from OpenAPI and no public Submission
      mutation or compatibility route appears.
- [ ] Existing hidden preparation, recovery, evidence, authorization, and
      admission behavior remains green.

## Implementation plan

1. Extend the ART preparation API with one strict blocked-feedback exception
   carrying `PreSubmissionExecutionFacts`; validate its exact type and
   ineligible disposition at construction.
2. Raise it at the existing ineligible branch after evidence completion. Do not
   alter execution, persistence, replay, admission, or transaction ordering.
3. Catch it before the generic preparation rejection and build the canonical
   422 error response directly from its bounded facts. Retain every other
   mapping unchanged.
4. Add a canonical multi-result fixture with a contributor-correctable failure,
   warning/dependency state, and bounded counts. Prove exact serialization,
   ordering, stable replay, redaction, distinct infrastructure mapping, no
   state mutation, and continued OpenAPI absence.
5. Reconcile the exact current docs, run focused and owner tests, then freeze a
   clean candidate for impact-routed review.

## Risk and review routing

- Risk class: `L1` — bounded contributor-visible error semantics across the
  CHECKERS/ART/API boundary; no authorization, persistence, lifecycle, or public
  route activation change.
- Required plan review: architecture, security, product/operations, and QA.
- Required implementation reviewers: architecture, security, product/operations,
  QA, test delta, documentation, and reuse/dedup.
- Human review focus: reuse of the canonical result projection; exact feedback
  usefulness and redaction; no false infrastructure-to-work-finding conversion;
  no accidental OpenAPI/public mutation activation; unchanged no-Submission
  boundary.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owner gap and reusable result contract | Inspect `PreparedSubmissionBundlePreparationCommand.prepare`, `PreSubmissionExecutionResult.bounded_facts`, `PreSubmissionExecutionFacts`, and `prepare_submission_bundle` | Confirmed before planning | Runtime proof pending implementation |
| Focused blocked/recovery behavior | `cd backend && .venv/bin/python -m pytest -q tests/test_submission_bundle_preparation_recovery.py tests/test_submission_bundle_admission.py` | Planned | PostgreSQL owner proof may require the broader default execution test |
| Canonical execution/evidence boundary | `cd backend && .venv/bin/python -m pytest -q tests/test_default_pre_submit_execution.py tests/test_pre_submit_attempt_contracts.py` | Planned | Hosted full-suite result remains PR evidence |
| Static quality and owner boundaries | `cd backend && .venv/bin/python -m ruff check app/api/routes/artifact_submissions.py app/modules/artifacts/api/submission_preparation.py app/modules/artifacts/submission_admission.py tests/test_submission_bundle_preparation_recovery.py tests/test_submission_bundle_admission.py` | Planned | Type-check target will follow the repository command available at implementation |
| No stale current claim or broken documentation link | `python3 scripts/check_stale_authorization_docs.py`; `python3 scripts/check_stale_artifact_contracts.py`; `python3 scripts/check_markdown_links.py`; `git diff --check` | Planned | Final central roadmap reconciliation remains with the lead |

## Review findings

No implementation review has run. The required L1 plan review must bind to the
committed planning head before application code begins.

## Reconciliation

- Current-source reconciliation: base `a51cf06cc`; B8 hidden completion delivery
  is complete, while 04F remediation, 04E3 production composition, ARCH-02I
  public activation, and the first-layer drill remain pending.
- Next usable boundary: after this hidden feedback foundation, 04F owns
  post-submit contributor correction and TASK replacement/recovery; 04E3 owns
  production registration/readiness; later ARCH-02I activates initial and
  remediation intake without a compatibility path.
- Remaining risks: the mounted hidden route is callable by authorized actors,
  so this response change is real behavior and requires exact redaction and
  replay proof even though it stays absent from OpenAPI.
