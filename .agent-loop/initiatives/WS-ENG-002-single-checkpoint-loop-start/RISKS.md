# RISKS: WS-ENG-002

- L1 workflow, authorization, audit, and signed-state change.
- A dispatcher identity mismatch must remain fail-closed.
- Feature-branch, stale-main, retry, arbitrary-successor, and concurrent publication defenses must remain unchanged.
- Historical two-person events must not be reinterpreted under the new dispatcher-authorized start schema.
- Cancellation must not inherit the reduced start checkpoint.
