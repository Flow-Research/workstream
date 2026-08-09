# WS-ART-001-04C2 External Review Response

## Comments addressed

- Verifier publication failure now converts the same fenced verification
  receipt and job to terminal `conflict`, preserving bounded attempt accounting
  without appending a contradictory second receipt.
- A partial unique database index now guarantees that one Submission ID cannot
  consume multiple admissions.
- Summary and contributor-attestation header values must be ASCII before they
  enter immutable packet evidence; invalid encoding returns bounded `422`.
- Locked task/predecessor/policy races now return bounded context-changed `409`
  rather than an internal error.
- The evidence policy-context constraint now uses the repository's logical
  naming-convention suffix.
- Alembic round-trip inspection now covers the evidence column/constraint,
  restored immutability trigger, and consumer uniqueness index.

## Comments deferred or declined

- The migration intentionally retains its local canonical-JSON implementation
  instead of importing mutable application code. Its encoding exactly matches
  `canonical_json_hash`, while keeping historical migration execution
  self-contained.
- CodeRabbit's generic docstring-percentage warning is not treated as a code
  failure: the repository's authoritative Agent Gates passed, and new boundary
  helpers have focused docstrings.
- Predicate-by-predicate negative publisher tests remain a low-risk follow-up;
  the current service-negative, database-trigger, and real concurrent workflow
  tests cover the complete fail-closed boundary.

## Human decisions needed

None.

## Commands rerun

- Focused Ruff and formatting for every changed response file.
- `git diff --check`.
- PostgreSQL migration upgrade from `0059` through `0061`.
- Canonical schema fingerprint validation after the new constraint and index.
- Focused admission tests and all hosted Backend lanes on the updated PR head.

## Remaining risks

AUTH activation and admission consumption remain separate reviewed chunks. The
route remains hidden and unavailable in this PR.

WS-QUAL-002-01 merged its protected exact module partition while this ART chunk
was in flight. The ready-admission publisher and hidden preparation command are
therefore consolidated in `submission_admission.py`; the QUAL-owned partition
is unchanged. Do not re-split those classes into new eligible Python modules
until a QUAL-owned protected-partition update has merged.
