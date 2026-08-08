# Chunk Contract: WS-POL-003-04A - Hidden Unified Setup

Status: Proposed after 03B; inactive. Risk: L1.

## Goal

Build the hidden one-attempt setup orchestrator and prove one complete result
contains sufficiency, artifact, pre-submit, and post-submit proposals together.

## Allowed files

Project setup worker/service/queue composition, unified compilation services,
focused project/authorization tests, and WS-POL-003 docs.

## Not allowed

Live worker routing, setup-ledger activation, approval, checker execution,
serialized handles/material, or any legacy inference fallback.

## Acceptance

- Automatic and manual recovery converge on one attempt/key/provider effect.
- Partial/malformed/unsafe output creates no component projection and
  terminally consumes the generation.
- Candidate call-graph tests prove all three legacy inference methods are
  unreachable and post-submit is already present in the unified result.
- No approval, continuation, replay, or recovery causes a second model call.

## Verification and review

Concurrent dispatch/recovery, same-key uncertainty, partial-result, static
reachability, and zero-second-call tests plus all L1 tracks. Human focus: one
complete result before any approval.
