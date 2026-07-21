# PLAN: WS-ENG-002

1. Add a cancellation-only approval job using the existing protected environment; the publishing job proceeds immediately for `start` and only after approval for `cancel`.
2. For starts, require the authenticated GitHub actor to appear in a closed allowlist on trusted `main`, collect immutable workflow-run evidence, and emit a versioned dispatcher-authorized envelope. GitHub's repository-writer restriction plus that reviewed allowlist is the authority boundary.
3. For cancellation, continue collecting and binding protected-environment approval evidence.
4. Validate both historical two-person envelopes and new dispatcher-authorized start envelopes without reinterpreting old records.
5. Update exact workflow/unit tests and engineering policy wording, including mixed-ledger and malformed-attribution cases.
6. Run deterministic checks and all required internal reviewer tracks.

When the user says `start`, the orchestrator performs the authenticated dispatch; chat itself is not canonical evidence. No automatic post-merge activation or chat-only authority is introduced.
