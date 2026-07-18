# ART <-> REV Handoff

## Boundary

REV owns review semantics: queue entries, leases, Reviews, findings, resolutions,
revision preparation, `ReviewPacketManifest`, and `ReviewEvidenceArtifact`. ART
owns immutable bytes, commitments, contents, replicas, receipts, verification,
bindings, provider execution, artifact recovery, and typed artifact capabilities.

Task/submission owns Submission version and task lifecycle. Checker owns
CheckerRun/CheckerResult semantics. REV references their stable IDs and ART
binding IDs without taking ownership of their records.

## Preconditions

- ART v2 is the only provider boundary. REV must not use the older
  verify/retain/release/provider-artifact contract in its current worktree.
- Submission and checker cutovers replace caller URI/hash authority with
  immutable ART binding IDs and server commitments.
- Required ART and REV actions have passed registration -> hidden behavior ->
  AUTH activation.
- Every protected ART service command first passes AUTH-09E fixed service
  admission for its exact static matrix row.
- Current review packet membership is derivable from canonical task,
  Submission, checker-run, revision-context, and binding relations.

## Review packet

`ReviewPacketManifest` is a REV-owned immutable projection. It names the exact
ReviewQueueEntry/ReviewLease, Submission version, admitting CheckerRun/results,
locked guide/revision context, response-evidence relations, and ART binding IDs.
It stores no bytes, provider ref, object key, signed URL, scratch path, receipt,
or authorization-matrix data.

An active ReviewLease authorizes bytes only for that exact current packet. Chain
history exposes bounded binding metadata, never bytes or provider details. A
prior, expired, consumed, sibling, later, cross-task, or cross-project lease
cannot read the packet.

REV authorizes `review.context.read` through AUTH and calls a narrow ART packet
read capability. ART revalidates each binding/content commitment and returns a
bounded stream; there is no generic human `artifact.retrieve` action and REV
does not call `artifact.binding.read`, which remains an Operator action.

## Reviewer evidence

`review.finding_evidence.ingest` and
`review.finding_response_evidence.ingest` are human product actions authorized
by AUTH. Byte intake is two-phase:

```text
request-scoped preflight authority
-> ART uploads/verifies an unbound candidate without review locks
-> finalization transaction begins
-> AUTH prepares and locks final human authority
-> REV locks lease/finding/response and packet lineage
-> ART locks candidate/admission/binding state
-> final typed facts are recomposed and AUTH evaluates once
-> ART binding plus REV evidence relation commit together
```

Provider I/O never occurs in the finalization transaction. Authority loss or
REV lineage drift can leave only an ART-owned unbound candidate under ART
retention; it creates no ReviewEvidenceArtifact relation or product effect.

Binding finalization uses the new closed service action
`artifact.review_evidence.binding.create`, mapped to the existing
`artifact.binding.create` PermissionId and assigned only to the existing
`workstream.artifact.binding` service identity. `AUTH_ART_REV_EVIDENCE` is its
AUTH activation custodian. AUTH registers it as planned; a future, separately
approved `WS-ART-001-REV-EVIDENCE` capability chunk would supply hidden
canonical resource facts, guards, binding behavior, and tests; AUTH would then
integrate the evaluator and alone activate it. This planning chunk neither
approves nor starts that future ART chunk. Existing Operator read actions and
generic PermissionId tokens cannot substitute for this ActionId.

## Review decision

Final review decisions consume only stabilized ART binding facts and the
verified submission-packet commitment. They perform no provider I/O. ART outage
or integrity uncertainty blocks judgment without creating `needs_revision`,
`reject`, or any other adverse product decision.

## ART owner response

ART must close binding request/model drift, add review-facing typed packet-read
and candidate/finalize ports, preserve exact project/task/submission ownership,
and return only stable IDs/commitments/bounded bytes.

## REV owner response

REV must define the packet/evidence schemas and relations, remove v1 provider
semantics and caller URI/hash authority, consume typed ART ports only, and keep
all Review lifecycle state and packet membership REV-owned.

## AUTH owner response

AUTH must register and activate exact review actions and any approved ART
review-evidence binding action only after both hidden implementations merge.

This handoff changes no runtime and starts no downstream chunk.
