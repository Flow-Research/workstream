# WS-REV-001 — Review and revision lifecycle

Exact pre-cutover work record: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Completed boundary: queue admission and ReviewLease persistence through 03A2.
- Intent: ensure the authorized reviewer evaluates the exact verified artifact
  under the locked policy version and produces attributable outcomes.
- Next usable boundary: continue hidden behavior behind exact AUTH, ART, and CON
  prerequisites; live claim requires the canonical review action gate.
- Governing sources: `docs/spec_review_lifecycle.md`,
  `docs/engineering/review_authorization_action_custody.md`, code, migrations,
  and tests.
- Preserve: only `accept`, `needs_revision`, and `reject`; immutable attempt
  policy lineage; separation of duties; and atomic final acceptance effects.

## Delivered

- Hidden review queue/admission persistence, ReviewLease, and preference
  persistence are merged through 03A2. REV policy identities and mutations and
  the fail-closed AUTH PREP/read handoff are available.
- No live claim or canonical review decision is implied by this foundation.

## Remaining v0.1 sequence

1. `03B`: normalized reviewer packet manifest after ART publishes the exact
   packet-membership contract.
2. Continue hidden claim/revision behavior against canonical `allow_review`,
   copying the Submission policy version without a current-policy lookup.
3. Implement Review and FinalAcceptance persistence plus the CON atomic
   participant; every final decision creates the reviewer record, and accept
   additionally creates the submitter record.
4. Activate public claim/decision behavior only after exact AUTH/ART/CON gates.
