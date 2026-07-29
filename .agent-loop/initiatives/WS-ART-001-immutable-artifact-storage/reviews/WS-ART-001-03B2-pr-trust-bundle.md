# PR Trust Bundle: WS-ART-001-03B2

## Chunk

`WS-ART-001-03B2` — Guide Materialization And Classification (L1)

## Goal

Read the exact verified guide-source object through the fixed guide-reader
boundary, recompute its complete identity in bounded private scratch, persist
only exact syntactic classification or bounded ART incident evidence, and keep
the behavior hidden until AUTH-04B.

## Human-Approved Intent

Project Manager guide items may be PDF, DOCX, PPTX, CSV, XLSX, Markdown, plain
text, JSON, or supported images; they are not contributor submission ZIPs.
03B2 classifies structure only. It does not extract semantics or invoke the
guide-sufficiency agent. Audio/video and ordinary/opaque ZIP content remain
unsupported in v0.1.

## What Changed And Why

- Extended the canonical materialization port and facade with exact guide reads.
- Added shared active namespace/store/replica validation before provider I/O.
- Added a typed scratch-owned inspection capability without exposing paths.
- Added complete rehash/size verification, pre/post lineage revalidation,
  immutable format classifications, and bounded custody incidents.
- Added deterministic PDF, OOXML, text-family, image, audio/video, ordinary ZIP,
  unsafe-container, and fixed-limit classification.
- Added migration `0040`, reset/fingerprint/lane updates, focused tests, and
  operator/deployment documentation.

This keeps the object store responsible only for bytes while Workstream owns
their identity, integrity, lineage, and meaning.

## Design Chosen

Transaction A locks and recomposes the exact binding/content/replica/receipt/
setup facts and consumes prepared read authority. Database locks are released
before the full provider read. The provider-neutral store streams into the
canonical scratch manager, which recomputes digest and size. Transaction B
relocks and recomposes the same facts before persisting one immutable result.

Alternatives rejected: direct S3/MinIO access, arbitrary temp files, caller
excerpts, parsing during HTTP upload, generic download authority, serialized
prepared handles, raw relationship substring checks, and a second materializer.

## Scope And Product Behavior

No route is exposed. `artifact.guide_source.read` remains planned/unavailable,
and positive behavior uses bounded test authority only. There is no extraction,
agent call, Celery continuation, submission/checker/review change, legacy
cutover, or new Operator API. Missing/corrupt/stale bytes are ART incidents,
never guide-insufficiency decisions.

## Acceptance Proof And Test Delta

Focused pure tests cover signatures, OOXML marker precedence, unsafe ZIPs,
fixed limit boundaries, image variants, typed inspection, deadline behavior,
and architecture fences. The isolated PostgreSQL runner passed all 13 selected
materialization tests after migrating through `0040`. They prove denial before
I/O, namespace drift, exact rehash, replay, changed/truncated/stale incidents,
cross-resource rejection, cancellation, timeout, and cleanup. Migration tests
cover classification-only and incident-only downgrade refusal.

No test, assertion, coverage threshold, workflow, or shard was weakened.
`test_guide_formats.py` is assigned to `shared_foundations`. Hosted repository
coverage (78 percent), artifact subsystem coverage (90 percent), Backend shards,
and Agent Gates remain required on the exact PR head.

## Reviewer Results And External Review

Architecture, security, QA, product/ops, CI integrity, docs, reuse, test delta,
and senior engineering pass after valid findings were repaired. CodeRabbit's
six low-severity comments were addressed; its generic docstring warning is
superseded by the repository-owned hosted docstring gate. GitHub Backend and
Agent Gates remain required on each repaired exact PR head.

## Remaining Risks And Follow-Up

The materializer facade contains only the guide-read slice today; 03B3A and
later chunks must extend it rather than create another path. 03B3A adds bounded
extraction; 03B3B adds remaining approved format extractors; 03B4 adds durable
same-generation continuation. Only then may AUTH-04B activate the fixed binding
and guide-reader actions. 03C remains a separate legacy cutover.

## Human Review Focus And Merge Ownership

Review the active namespace fence, pre/post setup-generation locking, complete
rehash comparison, classification precedence/limits, incident privacy, and the
deny-only AUTH boundary. Confirm the repaired nested-archive ceiling is enforced
before buffering and immutable classification conflicts cannot overwrite
evidence. The user retains the decision to mark the PR ready and approve its
merge.
