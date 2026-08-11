# Status: WS-POL-002 Post-Submit Checker Foundation

## Durable state on `main`

WS-POL-002-01 through WS-POL-002-03 are merged. They established the trusted
post-submit compiler contract, setup-time derivation and persistence,
pre-review handoff, server-owned approval/correction history, and bounded setup
visibility.

WS-POL-003 is authoritative for all future Project Guide inference. The old
POL-002-04 standalone inference/hardening sequence is not executable as written.
Any remaining executor behavior must be reframed as a bounded consumer of the
stored WS-POL-003 post-submit component and the current checker public API.

## Remaining boundary

No POL-002 implementation is active. A future executor-only change requires a
fresh contract against current `main`; it may not restore a second inference
path or rely on historical explicit-start and post-merge-memory instructions.

Open pull requests show transient work. Historical contracts and reviews remain
evidence for their exact changes, not an active queue.
