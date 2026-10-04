# Workstream CLI

An independent Go client for Workstream's public REST API, for humans and
agents using the terminal. The first slice provides two self-service reads:

| Command | Public API |
|---|---|
| `workstream whoami` | `GET /api/v1/actors/me` |
| `workstream project access PROJECT_ID` | `GET /api/v1/actors/me/authorization-context?project_id=PROJECT_ID` |

Workstream verifies the caller's Flow bearer and owns identity resolution,
authorization and lifecycle decisions. Reading a profile can admit a first-time
caller and update server-owned last-seen/audit data. Project access is a current
snapshot; each later API operation must independently authorize the caller.

## Build and use

Use Go 1.27.1, matching `go.mod` and CI. From this directory:

```sh
go build -trimpath -o /tmp/workstream-cli ./cmd/workstream
export WORKSTREAM_API_URL=https://your-workstream-api.example
# Supply WORKSTREAM_TOKEN through your existing secret environment mechanism.
/tmp/workstream-cli whoami
/tmp/workstream-cli project access PROJECT_ID --output json
```

`WORKSTREAM_API_URL` is the API origin, without `/api/v1`, credentials, query or
fragment. HTTPS is required except for loopback HTTP during local development.
`WORKSTREAM_TOKEN` contains the caller's unprefixed bearer value. It is forwarded
unchanged in the Authorization header. Avoid putting tokens in shell history;
the CLI reads its environment and does not save credentials. Configure the API
origin you trust to receive that credential. Redirects and ambient HTTP proxies
are disabled; system certificate verification remains enabled.

The binary runs independently of Python, the backend source tree and MCP. The
source package is buildable; published binaries, installers and signing are a
later release boundary. The [CLI initiative](../.commitrail/initiatives/WS-CLI-001/OVERVIEW.md)
describes subsequent public workflows and an optional TUI.

## Output and automation

Commands need no TTY or interactive prompts. Default human output escapes
terminal control characters in API text. `--output json` (or `-o json`) writes
the successful API object to stdout without a wrapper. Failures leave stdout
empty and write bounded error metadata to stderr; JSON errors use an `error`
object with `code`, optional HTTP `status`, and optional `correlation_id`.
Raw error bodies and transport exceptions are not printed.
Server error codes and correlation headers containing the caller's bearer
are suppressed, including case-only reflections. Success responses require
valid UUID identities and non-null string array members. Project access compares
UUID identity rather than spelling, while sending the supplied selector unchanged
and preserving the successful API JSON.

Exit status is `0` for success, `1` for API/network/response failure, and `2`
for invalid arguments or configuration. A request times out after 12 seconds;
responses are bounded to 64 KiB and requests are not automatically retried.
Use `--help`, `--version` and `completion bash|zsh|fish|powershell` without a
credential or network connection.

## Verification

Behavior tests invoke the built executable from outside the repository, with
no import of Go internals. One suite uses a controlled HTTP server to exercise
credential/destination safety, output and failure boundaries. The other uses
the current FastAPI app with isolated real PostgreSQL to prove first admission,
profile fields, authorized exact-project context and foreign-project denial.
Local Flow-compatible tokens are test fixtures, not deployed-provider proof.
No coverage percentage or test-count target is used.

```sh
go mod verify
go vet ./...
go build -trimpath -o /tmp/workstream-cli ./cmd/workstream
# With the backend test environment installed:
WORKSTREAM_CLI_EXECUTABLE=/tmp/workstream-cli python -m pytest -q tests/integration/test_http_boundary.py
# From backend/, with a local disposable PostgreSQL admin URL in the environment:
WORKSTREAM_CLI_EXECUTABLE=/tmp/workstream-cli python scripts/run_isolated_tests.py --metadata-json /tmp/workstream-cli-isolation.json -- python -m pytest -q ../cli/tests/integration
```

The real API fixture uses the documented local administrator bootstrap solely
to arrange test authority, then creates its project through public APIs. These
test dependencies are absent from the shipped CLI. See the workflow for the
complete [hosted check](../.github/workflows/cli.yml).
That reusable check runs in parallel with Backend lanes; its failure also fails
the existing required Backend `test` result. No separate optional PR workflow
or extra branch-protection setting is needed.
