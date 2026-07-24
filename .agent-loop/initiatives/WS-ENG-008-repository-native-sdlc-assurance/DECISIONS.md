# Decisions: WS-ENG-008 — Repository-Native SDLC Assurance

## D1 — Preserve the zero-trust loop as the enforcement mechanism

“Repository-Native Human-Agent SDLC” names the broader development model. The
Codex-native zero-trust engineering loop remains its enforcement mechanism and
is not renamed away.

## D2 — Enforce future contracts without guessing historical intent

Machine scope applies to every implementation/specification contract changed in
a PR whose base contains the `WS-ENG-008-01` merge intent. Chunk 01 must upgrade
its already-reviewed ENG-008 successors 02–07 before selecting 02. Unchanged
pre-cutover contracts are the only grandfather set and remain governed by their
reviewed evidence and existing gates.

## D3 — Keep scheduled drift verification read-only

The scheduled job can detect and report but cannot sign, repair, push, dispatch,
approve, or merge.

## D4 — Route adversarial proof instead of adding a universal reviewer

Risk routing assigns explicit adversarial proof to high-risk work using existing
review ownership. Evidence records attempts and outcomes, not an empty file.

## D5 — Measure mutation quality before setting a threshold

The pilot is non-blocking and cannot reduce existing coverage gates. A blocking
mutation policy requires a later reviewed human decision based on hosted data.

## D6 — Reconcile concurrent initiatives at every boundary

Planning uses current signed state, but each implementation start, review,
publication, and merge repeats current-main and overlap checks. AUTH property
work and root-log archival have explicit concurrency waits.

## D7 — Archive review memory losslessly

Root review memory becomes an index only after byte-preserving archives and
link/reconstruction proof exist. Initiative review directories remain detailed
evidence.
