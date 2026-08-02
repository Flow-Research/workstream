# Chunk Contract: WS-ART-001-04C2 — Ready Admission Publication

Parent initiative: `WS-ART-001` | Risk: L1 | Status: Proposed after 04C1

## Goal

Publish one immutable capacity-charged ready admission after exact read-back
verification and compose the hidden continuous contributor endpoint.

## Allowed Files

SubmissionBundleAdmission model/migration/repository, verification publication
integration, bounded Operator projection, hidden route composition, tests/docs/CI.

## Not Allowed Changes

Submission/binding consumption, public activation, expiry/release/delete,
candidate storage, review/contribution, or new recovery machinery.

## Acceptance Criteria

Only verified matching bytes publish ready; lifecycle is ready->consumed|stale;
actor/link/project/task/assignment/predecessor/context/manifest/evidence lineage
is immutable; abandoned ready remains charged; exact POST replay returns the
same operation/admission; 04A2-04C2 run in one request with no serialized local
handle; fixed pre-submit materializer is active before later live activation.

## Verification Commands

Focused verification/publication/lifecycle/concurrency/operator tests, Ruff,
hosted gates, 90% owned subsystem and 78% repository coverage.

## Required Reviewers

Security/auth, architecture, QA, product/ops, senior, CI, docs, reuse, test delta.

## Human Review Focus And Stop Conditions

No bindable admission exists before complete verification; no abandoned state
causes product lifecycle effects.
