# INTENT: WS-ENG-002 — Single-Checkpoint Loop Start

## Problem being solved

An explicit user start currently requires a second protected-environment approval before the signed loop-memory event can run.

## Why this work matters

The duplicate checkpoint adds delay without adding a distinct human decision. GitHub already authenticates the workflow dispatcher and restricts workflow dispatch to repository writers.

## Current behavior

The dispatcher starts the workflow, then a different environment reviewer must approve it.

## Target behavior

One authorized GitHub workflow dispatch is the explicit human start. The signed event remains bound to its dispatcher, run, current `main` SHA, prior state tip, initiative, chunk, and reason.

## Design chosen

Bypass the environment gate only for `start` when the authenticated dispatcher appears in a fixed allowlist reviewed on trusted `main`, and record a new explicit dispatcher-authorized event envelope. Preserve the protected-environment approval for `cancel`, preserve historical two-person event validation, and preserve all replay, SHA, successor, signing, validation, and publication controls.

## Alternatives considered

- Automatic start after merge: rejected because it removes the explicit human checkpoint.
- Chat as unsigned state input: rejected because canonical memory needs GitHub-verifiable evidence.
- A second environment approval: rejected as the redundancy being removed.

## Boundaries preserved

No product behavior, cancellation authority, merge authority, signing key, state branch, successor rule, or protected-main rule changes.

## Expected risks

Accidentally weakening event attribution or permitting stale/arbitrary starts.

## What must not change

Starts remain explicit, successor-bound, signed, serialized, and auditable. Cancellation retains protected-environment approval. Merges still require specific user approval.

## How this will be proven

Workflow structure tests and authority-event unit tests will prove single-dispatch authorization and preserved fail-closed bindings.

## Human decisions required

The user approved immediate implementation for ordinary starts on 2026-07-21. Chat is an instruction to the orchestrator, not canonical evidence; the orchestrator's authenticated GitHub dispatch creates the signed canonical evidence.
