# Decisions: WS-POL-002 - Post-Submit Checker Foundation

## D1. Post-Submit Policy Is Project-Scoped

`PostSubmitCheckerPolicy` remains attached to the project guide/source snapshot
context. Tasks lock the applicable project policy. Tasks do not derive,
compile, or own unique post-submit checker policies.

## D2. Agent Derivation Happens During Setup Only

The post-submit policy derivation agent runs during project setup. It receives
locked guide/source material plus relevant project policy context and emits a
constrained checker specification.

The agent does not evaluate worker submissions.

## D3. Runtime Is Deterministic

Runtime post-submit evaluation executes Workstream-registered deterministic
checkers only. v0.1 does not allow arbitrary generated checker code as the
default path.

## D4. Defaults Cannot Be Weakened

The default durable post-submit checkers always run. Project-specific policy may
add registered checkers or tighten routing/severity, but it cannot remove
default checks or downgrade their required coverage.

## D5. Unsupported Required Checks Block Setup

If the project guide implies a required post-submit check that cannot be
represented by registered deterministic checker primitives, setup must surface a
clear blocking gap. Workstream must not silently ignore it or pretend the
project is fully protected.

## D6. Manual Guide Payload Is Obsolete

The long-term contract removes client-authored `post_submit_checker_policy`
from guide create/update request bodies. Workstream owns generated post-submit
policy setup and approval. No backward compatibility alias should be added once
the server-owned path replaces the manual payload.

## D7. Worker-Facing Outcomes Stay Simple

Post-submit checker failure that the worker can fix routes to `needs_revision`.
Internal setup defects and trusted checker failures stay in internal repair
routes and are hidden from worker-facing checker results.

## D8. Evidence Must Be API-Visible

The final proof must use API-visible setup runs, generated policy outputs,
task locked context, submission finalization, checker runs, audit events, and
task status. Database inspection is not accepted as lifecycle proof.
