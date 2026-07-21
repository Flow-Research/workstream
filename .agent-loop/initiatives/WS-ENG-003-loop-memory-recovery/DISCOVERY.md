# DISCOVERY: WS-ENG-003

- Loop Memory run `29811288198` failed at `apply_merge_record` with `post-cutover merge has no signed start or exemption` for PR #166.
- Canonical automation state remains at the successful ART PR #159 merge and is uncorrupted.
- `apply_merge_record` already supports exact, consumable exemption tuples and preserves remaining inventory.
- The legacy inventory is intentionally loaded only from the immutable WS-ENG-001-04B cutover commit and must not be rewritten.
- The recovery PR number is unknowable before PR creation, so its exact identity must be derived from its trusted merge record rather than hard-coded early.
- The workflow processes every missing first-parent merge in order from the existing signed state to its exact target SHA.
- Therefore recovery must be collected and validated before the first sequential update; waiting for the reducer to reach the recovery merge cannot unblock PR #166.
