# External Review Response

## Chunk

`WS-MCP-001-01`

## Status

[PR #149](https://github.com/Flow-Research/workstream/pull/149) received an
initial CodeRabbit review with nine inline findings and one summary nitpick,
followed by ASGI buffering and direct test-dependency findings. The maintainer
also requested complete agent-facing tool contracts. All current findings are
addressed through reconciled head `f5b519c`, with current `main` at `5a8a924`
integrated without changing MCP package or workflow files.
CodeRabbit and GitHub checks must rerun after the final evidence commit is
pushed.

## CodeRabbit Findings

| Finding | Disposition | Evidence |
|---|---|---|
| Restrict the MCP job token permissions. | Addressed | The MCP job declares `permissions: contents: read`; checkout credentials remain disabled. |
| Enforce 90 percent MCP coverage. | Addressed | CI runs pytest-cov with `--cov-fail-under=90 --cov-precision=2`; the current result is 95.27 percent. |
| Reuse an HTTP client across composed reads. | Addressed | Task Context and Task Status create one operation-scoped client, reuse it for every subrequest, and close it; a focused regression proves creation count and closure. |
| Redact secrets inside sets. | Addressed | Recursive set redaction and a regression canary were added. |
| Hide completed review lease/routing details. | Addressed | `none_available` now returns only source, project, and state. |
| Check review replay before fixture matching. | Addressed | `claim_review` performs actor-scoped replay/conflict validation before availability checks. |
| Propagate `needs_revision` to task state. | Addressed | Findings and reviewed submission version persist into Task Status/Context; revised submission requeues a new review. |
| Mark replay results for telemetry. | Addressed | Replayed copies carry `idempotent_replay=true` without mutating cached results. |
| Make relative-path validation reachable. | Addressed | `.` and `..` are rejected before the general stable-reference pattern. |
| Require secure explicit HTTP auth issuer configuration. | Addressed | Streamable HTTP requires an explicit HTTPS issuer, with deliberate loopback-only development override. Workstream Auth verifies tokens before MCP HTTP context is created. |
| Bound unconstrained submission inputs. | Addressed | Submission strings/collections, finding lists, evidence references, metadata depth/size, and HTTP request bodies are bounded. |
| Bound buffered ASGI messages, not only body bytes. | Addressed | Authenticated bodies are coalesced with 2 MiB, 1,024-frame, and 30-second limits; oversized frames are rejected before copying, anonymous bodies bypass buffering for immediate `401`, and replay delegates to the real receiver so SSE remains live. |
| Declare directly imported `sse-starlette`. | Addressed | `sse-starlette>=3.0,<4.0` is a direct development dependency and installs with `.[dev]`. |
| Keep output validation out of the input-validation sanitizer. | Addressed | Output model failures become safe `unexpected_server_error` results inside the observed operation; client `isError` and infrastructure-error telemetry are both protocol-tested. |

## Maintainer Agent-Facing Contract

- All seven tools publish full what/when/not/prerequisite/side-effect/outcome
  guidance and the next resource to read.
- Actual decorated parameters publish descriptions, constraints, defaults, and
  examples, including explicit UUID idempotency instructions and nested packet
  fields.
- All seven tools publish structured Pydantic output schemas. Execution and
  validation failures set `isError=true`; a coherent completed checker failure
  remains a valid negative result.
- Resource and tool titles/descriptions come from the static catalogue and are
  verified through the official SDK protocol.

## Additional Internal Findings

- Added `--cov-precision=2` so a rounded value below 90 percent cannot pass.
- Disabled HTTPX environment-proxy inheritance for bearer forwarding.
- Prevented Streamable HTTP from falling back to the STDIO process token.
- Added an operator-facing MCP README for required transport/auth configuration.
- Added reviewed-submission references to revision context and completed the
  temporary revision-to-review loop.
- Preserved real ASGI disconnect delivery after bounded replay and added a real
  MCP SDK Streamable HTTP SSE journey.
- Rejected missing or invalid bearer requests before body buffering while
  retaining byte, frame, and receive-deadline limits for authenticated bodies.
- Sanitized SDK validation errors so invalid parameter values cannot echo the
  active bearer token.
- Required strict, coherent checker responses and exact review-context references
  before publishing successful MCP outcomes.
- Expanded protocol regressions; the complete package has 95.27 percent coverage.
- Redacted exact compact UUID equivalents even when an overlapping hexadecimal window precedes them.
- Preserved retryable Auth outages as HTTP `503` responses instead of reporting invalid contributor credentials.
- Documented the production capability boundary and a collision-free local Streamable HTTP topology.

## GitHub Checks

Pending on the final evidence head after push. Fork-triggered jobs may still
require maintainer approval.

## Notes

Do not resolve the review as complete until reconciled head `f5b519c` and its
evidence commit are pushed and CodeRabbit/GitHub checks report against that head.
Do not merge without explicit human approval.
