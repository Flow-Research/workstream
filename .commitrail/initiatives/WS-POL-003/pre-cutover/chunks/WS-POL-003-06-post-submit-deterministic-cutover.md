# Planning Parent: WS-POL-003-06 - Deterministic Post-Submit Cutover

Status: Split into `06A` and `06B`; this file is not executable. Risk: L1.

`06A` builds hidden trusted projection/approval behavior from the post-submit
component already stored in the unified result. AUTH-12G activates the exact
service and human boundaries. `06B` exposes them. Replay, recovery, and a
correction request against existing compilation provenance perform zero
additional model calls. A correction that requires a new unified generation is
a separate compilation attempt with its own idempotency key; it is not replay
or recovery of the prior attempt.
