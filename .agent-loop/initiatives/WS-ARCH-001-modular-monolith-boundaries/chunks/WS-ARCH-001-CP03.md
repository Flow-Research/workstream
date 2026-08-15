# Chunk Contract: WS-ARCH-001-CP03 — Adapter-Binding Activation Split Parent

## Status

Split and non-executable.

## Goal

Coordinate the two independently reviewable prerequisites for safe
adapter-binding activation.

## Approved split

```text
CP02 hidden lifecycle behavior
-> CP03A compensation-adapter identity and owner eligibility
-> CP03B exact Finance Authority AUTH activation
-> CP04 hidden ContributionPolicy behavior
```

CP03A owns no AUTH action activation. CP03B owns no identity registration,
schema change, or owner eligibility behavior. Neither child adds a public
adapter-binding route.

## Merge state

- Outcome on merge: `split parent recorded; no runtime behavior`
