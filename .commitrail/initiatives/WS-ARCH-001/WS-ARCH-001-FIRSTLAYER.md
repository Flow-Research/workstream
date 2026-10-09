# WS-ARCH-001 — Reconcile the remaining first-layer sequence

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: Current navigation distinguishes delivered foundations
  from the five remaining outcome groups and orders authorized consequences before
  completion-handler delivery.

## Intent

The user reaffirmed the first usable contributor journey and asked whether the
work had drifted. Existing B4/B5/B6/B7 and REV-12A4A records support the completed
prerequisites; they do not establish a publicly usable end-to-end path. The
current nine-step table mixed those completed boundaries with remaining work.
Some summaries still assigned initial dispatch or completion-handler wiring
before the complete authorized operation it must consume.

The recent implementation serves the agreed journey, including the explicitly
approved controller/payment-deferral decision. This reconciliation corrects
navigation; it does not claim every historical scope choice was necessary or
that an internal implementation is live.

## Bounded change

Allowed: this record; ARCH `planning/PLAN.md`, `planning/CHUNK_MAP.md`,
`OVERVIEW.md`; the active `planning/chunks/WS-ARCH-001-04E-canonical-allow-review.md`
coordination contract; `.commitrail/INDEX.md`; `docs/roadmap_status.md`; local roadmap
XLSX/CSV exports only if present.

Not allowed: product code, tests, schemas, permission changes, new prerequisites,
activation, historical completed-record rewrites, or a new parallel plan/status
system. Keep the existing plan as the governing sequence. No standalone product
feature or additional prerequisite is introduced.

## Acceptance criteria

- Separate delivered checked-input, Submission/dispatch, request-handler and
  shared-participant/controller foundations from remaining implementation.
- Five remaining groups: authorized outcomes then completion delivery;
  remediation/recovery; live composition; public intake/outcomes; real drill.
- The complete authorized operation precedes completion-handler acknowledgment.
  A preparation-only receipt never substitutes for its committed effects.
- Preserve default-true review policy and its independent human-review handoff;
  false/pass creates shared acceptance, submitter contribution and applicable
  awards atomically. No fabricated Review or reviewer contribution.
- Keep live human review/revision, contributor expiry/skip, fulfillment/payment
  delivery, reputation and unrelated integrations outside this immediate milestone.
- Require each future bounded record to name its remaining group, reused owners,
  observable gap and proof; additional foundations need a demonstrated blocker.
- Do not equate five groups with five PRs or claim end-to-end readiness before the
  real PostgreSQL/storage/broker drill passes.

## Risk and review routing

Risk: L1 sequencing of authorization/workflow work; documentation-only change.
Required reviews: architecture/plan feasibility and documentation/product-ops.
Human focus: does the order finish the agreed first contribution journey without
adding deferred work? No new human scope decision is required.

## Evidence

Verify changed Markdown links, Commitrail records, diff whitespace and a targeted
scan for stale next-step/nine-step instructions. Compare current claims with
merged owners and existing change records; no runtime behavior changes or new
runtime tests are warranted. No local spreadsheet exports are present.

## Reconciliation

Base: merged #516 and #517. Next implementation remains the existing ARCH-04E2-B
complete authorized outcome operation, then ARCH-04E1B-B completion delivery.
The first layer is still incomplete. This is a current-plan correction, not
another product prerequisite. Exact review/check evidence belongs in the PR.

## Review correction

Architecture and documentation inspection found additional handler-first wording
in current summaries and the linked pending 04E coordination contract. Reconcile
those current instructions to the same authorized-operation-before-completion
order; preserve historical completed records. No runtime capability is added.
