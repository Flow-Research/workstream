# WS-ARCH-001-02E Admission And Binding Manifest

## Public capability

`app.modules.artifacts.api.SubmissionAdmissionConsumptionPort.consume` accepts
one immutable `SubmissionAdmissionConsumptionRequest` and returns one bounded
`SubmissionAdmissionConsumptionResult`. The request contains the ART admission
identifier, the TASK-supplied immutable Submission identifier and version, and
the transaction-locked `TaskSubmissionContextFacts` capability from 02A.

No authorization handle, ORM row, provider selector, byte stream, or route
schema crosses this public boundary.

## Locked ART resources

The owner-local service locks and validates:

- `SubmissionBundleAdmission` by exact admission identifier;
- its exact `PreSubmitEvidenceSet` lineage;
- its exact immutable `ArtifactContent` digest and byte count;
- any existing generic `ArtifactBinding` for the supplied Submission identity.

The TASK capability supplies task, assignment, contributor, predecessor,
project, guide version, source snapshot, effective submission-artifact policy,
and pre-submit checker policy facts. ART compares those facts with its own
persisted evidence and admission lineage without importing or querying TASK
persistence.

## Authorization and mutation order

1. Concealment authorization runs before admission lookup.
2. ART locks and validates the exact admission, evidence, content, and TASK
   capability facts.
3. Exact binding authority consumes the complete actor/identity-link, admission,
   evidence, TASK, predecessor, guide/snapshot/policy, manifest, Submission,
   content, digest, byte-count, and logical-role facts.
4. ART creates one generic `ArtifactBinding` and marks the admission consumed
   in the caller-owned root transaction.

The production default denies both authorization phases. AUTH activation and
TASK transaction composition remain later chunks. No public route reaches this
capability in 02E.

## State and replay

- `ready -> consumed` creates one binding with resource type `submission`,
  logical role `submission_bundle_original`, and the exact Submission version.
- Exact replay for the same Submission and version revalidates full lineage,
  consumes fresh final authority, and returns the existing binding.
- A different Submission receives
  `submission_bundle_admission_already_consumed`.
- Proven TASK context replacement permits only
  `ready -> stale` with `locked_submission_context_changed`.
- Authorization denial, broken/missing ART lineage, cancellation, or transaction
  rollback leaves the admission unchanged.
- `consumed` and `stale` are terminal.

No provider I/O, Submission creation, expiry, deletion, retention, or capacity
release occurs in this capability.

## Stable ART errors

- `submission_bundle_admission_unavailable`
- `submission_bundle_admission_already_consumed`
- `submission_bundle_admission_context_changed`
- `submission_bundle_admission_stale`
