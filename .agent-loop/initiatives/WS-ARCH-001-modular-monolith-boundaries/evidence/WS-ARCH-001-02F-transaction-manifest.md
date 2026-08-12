# WS-ARCH-001-02F Transaction Manifest

## Capability

The hidden `SubmissionCreationCommand` creates one TASK-owned immutable
Submission from one already-ready ART admission. It remains route-unreachable
and production authorization remains deny-only.

## Transaction and lock order

1. The TASK adapter opens one root SQLAlchemy transaction.
2. Human `submission.create` authority is checked through the TASK-owned typed
   authority port before TASK state is revealed.
3. TASK locks the task, active assignment, and latest predecessor.
4. TASK allocates the Submission UUID and version.
5. TASK inserts and flushes the provisional Submission identity/version.
6. ART consumes the exact admission and fixed binding authority through its
   public port, locking ART lineage and binding scope.
7. TASK completes and flushes the immutable Submission with admission, binding,
   content, assignment, predecessor, and locked policy references.
8. TASK consumes final human authority using the allocated identity/version.
9. The adapter commits once; every exception or cancellation rolls back all
   participants.

## Public facts and ports

- `SubmissionCreationRequest` carries contributor-authored summary and
  attestation plus server-selected TASK/assignment/admission/predecessor IDs.
- `SubmissionCreationAuthorizationPort` exposes only preliminary and final
  TASK facts; no AUTH handle, context, repository, or session crosses TASK.
- `SubmissionArtifactAdmissionPort` is the TASK-owned participant protocol;
  the composition adapter translates it to ART's public
  `SubmissionAdmissionConsumptionPort`.
- `SubmissionCreationResult` returns only Submission, admission, binding, and
  content identities.

## Protected mutations

- TASK: one immutable `submissions` row.
- ART: one admission terminal transition and one generic artifact binding.
- AUTH: transaction-local decision evidence only after later activation.

Pre-submit checker evidence is an immutable prerequisite and is not mutated by
this command.

## Deny-only state

`DenySubmissionCreationAuthorization` rejects before TASK locks or mutation.
No route, action catalogue entry, or production AUTH adapter is activated by
02F. Positive complete-effect and concurrency proof remains owned by 02H.
