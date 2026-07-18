# External Review Response

## Chunk

`WS-MCP-001-01`

## Status

[PR #149](https://github.com/Flow-Research/workstream/pull/149) received a
CodeRabbit review with nine inline findings and one summary nitpick. All ten
findings are addressed in local remediation commit `a9504ea`; CodeRabbit and
GitHub checks must rerun after that commit is pushed.

## CodeRabbit Findings

| Finding | Disposition | Evidence |
|---|---|---|
| Restrict the MCP job token permissions. | Addressed | The MCP job declares `permissions: contents: read`; checkout credentials remain disabled. |
| Enforce 90 percent MCP coverage. | Addressed | CI runs pytest-cov with `--cov-fail-under=90 --cov-precision=2`; the current result is 93.71 percent. |
| Redact secrets inside sets. | Addressed | Recursive set redaction and a regression canary were added. |
| Hide completed review lease/routing details. | Addressed | `none_available` now returns only source, project, and state. |
| Check review replay before fixture matching. | Addressed | `claim_review` performs actor-scoped replay/conflict validation before availability checks. |
| Propagate `needs_revision` to task state. | Addressed | Findings and reviewed submission version persist into Task Status/Context; revised submission requeues a new review. |
| Mark replay results for telemetry. | Addressed | Replayed copies carry `idempotent_replay=true` without mutating cached results. |
| Make relative-path validation reachable. | Addressed | `.` and `..` are rejected before the general stable-reference pattern. |
| Require secure explicit HTTP auth issuer configuration. | Addressed | Streamable HTTP requires an explicit HTTPS issuer, with deliberate loopback-only development override. Workstream Auth verifies tokens before MCP HTTP context is created. |
| Bound unconstrained submission inputs. | Addressed | Submission strings/collections, finding lists, evidence references, metadata depth/size, and HTTP request bodies are bounded. |

## Additional Internal Findings

- Added `--cov-precision=2` so a rounded value below 90 percent cannot pass.
- Disabled HTTPX environment-proxy inheritance for bearer forwarding.
- Prevented Streamable HTTP from falling back to the STDIO process token.
- Added an operator-facing MCP README for required transport/auth configuration.
- Added reviewed-submission references to revision context and completed the
  temporary revision-to-review loop.
- Expanded safe tool-error tests; `tools.py` now has 94.79 percent coverage and
  the complete package has 93.71 percent coverage.

## GitHub Checks

Pending on the remediation head after push. Fork-triggered jobs may still
require maintainer approval.

## Notes

Do not resolve the review as complete until the remediation commit is pushed
and CodeRabbit/GitHub checks report against that head. Do not merge without
explicit human approval.
