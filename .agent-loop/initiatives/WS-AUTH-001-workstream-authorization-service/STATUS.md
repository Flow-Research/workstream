# Status: WS-AUTH-001 Workstream Authorization Service

WS-AUTH-001-14 is a planned retirement as a superseded/non-executable broad
cutover; WS-ARCH-001-03C/04D/04E/04F and later REV/public cutover own its split
replacement.

## Durable state on `main`

AUTH provides the central deny-by-default authorization boundary for Workstream.
Merged behavior includes external Flow-token verification, canonical actors and
identity links, request context and rate controls, authority audit and
idempotency, closed permission/action catalogues, project-scoped grants,
bootstrap administration, fixed-service identities and runtime admission,
controlled provisioning, actor/identity administration, and the implemented
project read and mutation cutovers.

Project Guide compilation request/recovery and fixed project-setup execution
authority merged through `WS-AUTH-001-12I` in PR #312. That activation exposes
authority for the hidden POL compilation path; it does not make the remaining
POL, ART, REV, CON, TASK, or checker lifecycle behavior live.

All completed and superseded AUTH chunks remain enumerated in `CHUNK_MAP.md`.
Their contracts, reviews, and Git history are historical exact-change evidence,
not current start requirements.

## Remaining boundaries

- `WS-POL-003-03B` consumes merged AUTH-12I before the next unified setup
  orchestration boundary.
- AUTH-12B2 follows hidden POL-04A and activates only setup-ledger authority.
- AUTH-12F4 follows hidden POL-05A and activates approval of stored unified
  pre-submit policy; it performs no inference.
- AUTH-12G follows hidden POL-06A and activates deterministic stored
  post-submit projection authority.
- WS-AUTH-001-12H is planned after complete POL-06B/07, corrected AUTH-12B2, CP05 active
  ContributionPolicy behavior, CP06 validation, and CP07 ProjectGuide binding.
  It does not depend on CP08, WS-ARCH-001-03A/03B/03C, or CP09 final legacy
  removal.
- AUTH-13 through AUTH-16 remain future task, submission/checker, cleanup, and
  conformance boundaries. Each must be split against then-current product
  behavior before implementation.
- ART, REV, and CON feature actions remain unavailable until their exact hidden
  owner behavior and typed manifests are merged. Their activation order lives
  in the matching XINT and feature-owner records.
- PLAN3 proposes the missing contribution-policy sequence: CP01 registers exact
  adapter-binding and policy actions while unavailable; CP03 and CP05 activate
  only their respective merged hidden behavior. Fulfillment callback authority
  remains separate and cannot be bundled into adapter-binding registration.

Open pull requests are the transient-work view. This status page does not name
an active branch or authorize implementation. GitHub permissions, a bounded
contract or PR-stated scope, tests, review, and human merge govern each change.

## Historical evidence

The former signed-start, single-active-chunk, and post-merge-memory process is
retired. References to it in old contracts and review evidence describe how
those exact historical changes were produced and must not be executed as
current workflow instructions.
