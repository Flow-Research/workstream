# Read-only GitHub access for the Garden drill

The external image receives bounded facts, never GitHub credentials. Configure
the existing Workstream GitHub App adapter on the outbox worker that reads
those facts. The API and its migration process do not consume this credential.
Do not place the private key in a checker image, ZIP, guide or PR.

An organization owner or authorized App manager registers the App under
Flow-Research's Settings → Developer settings → GitHub Apps. Use a descriptive
unique name and the Workstream repository as its homepage. Leave OAuth callbacks
unused and disable active webhooks: this reader fetches facts on demand.
See [GitHub's registration instructions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app).

Set only these repository permissions, all **read-only**:

| Permission | Current reader use |
|---|---|
| Administration | Required checks on the protected target branch |
| Checks | Check runs and trusted producer identity |
| Commit statuses | Commit status results |
| Contents | The Git commit object for the exact PR head |
| Pull requests | PR state, reviews and changed files |
| Metadata | Repository facts and reviewers' current repository permissions |

Keep organization and other repository permissions at No access. Administration
read is required for branch-protection inspection, not permission to change it.
The [GitHub App endpoint permission reference](https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps)
maps these scopes to the reader's endpoints.

Install the App on Flow-Research with **Only select repositories → garden**.
An organization owner may need to authorize installation because it requests
repository Administration read. Record the numeric App ID, not its OAuth Client
ID, and generate a private key from the App settings. Store the PEM in an
operator-only location outside Git. Do not paste its contents into chat or logs.

The existing settings are:

```dotenv
WORKSTREAM_GITHUB_APP_ID=<actual numeric App ID>
WORKSTREAM_GITHUB_APP_PRIVATE_KEY_FILE=<absolute operator-only PEM file path>
WORKSTREAM_GITHUB_APP_INSTALLATION_ID=
```

The placeholders above are not runnable configuration. Hosted release preflight
requires the App ID and key file together; the checked optional GitHub overlay
mounts the key only into the worker. Store the complete multiline PEM in a regular
file owned by the runtime UID/GID with mode `0400`. The worker entrypoint loads
the adapter's existing `WORKSTREAM_GITHUB_APP_PRIVATE_KEY` variable; do not put
that raw value in the release environment file. The optional
`WORKSTREAM_GITHUB_APP_INSTALLATION_ID` can remain unset: the adapter discovers
the installation for the exact repository. The API origin defaults to
`https://api.github.com`. It requests a repository-scoped
installation token; no personal-token or anonymous fallback is used.

After configuration, verify a bounded facts read for a real Garden PR through
the actual adapter, including exact-head commit retrieval and required branch
checks. Confirm installation scope and errors without printing credentials,
private response bodies or tokens. A successful health endpoint alone does not
prove GitHub access. The version-2 test explicitly sets the Garden POST
`required_independent_approvals` to zero; omission still requires one, and shared
Harnessy still requires at least one. Keep the reader permissions for supported
positive-count policies; zero does not manufacture approval facts or waive real
merge, trusted CI or exact task association. Workstream's separate
`human_review_required=false` setting remains unchanged.

The complete success path still needs an actually merged task-associated PR and
the public Submission/contribution journey. Leave PR #287 open as requested;
no successful merged-work outcome is claimed for it. Earlier guide/task/image
evidence remains retained, and v2 needs new publication and approvals.

See the [project guide](guide.md), [drill plan](README.md), and
[shared forge boundary](../../docs/engineering/local-agent-loop.md).
The [hosted release instructions](../../deploy/hosted/README.md) describe secret provisioning.
