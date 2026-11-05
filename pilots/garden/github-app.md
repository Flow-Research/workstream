# Read-only GitHub access for the Garden drill

The external image receives bounded facts, never GitHub credentials. Configure
the existing Workstream GitHub App adapter on the API and worker host that reads
those facts. Do not place the private key in a checker image, ZIP, guide or PR.

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
| Contents | The Git commit object for the exact reviewed head |
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
WORKSTREAM_GITHUB_APP_PRIVATE_KEY=<private PEM supplied through the secret environment>
WORKSTREAM_GITHUB_API_BASE_URL=https://api.github.com
```

The placeholders above are not runnable configuration. The adapter accepts
multiline PEM or literal escaped newline separators. The optional
`WORKSTREAM_GITHUB_APP_INSTALLATION_ID` can remain unset: the adapter discovers
the installation for the exact repository. It requests a repository-scoped
installation token; no personal-token or anonymous fallback is used.

After configuration, verify a bounded facts read for a real Garden PR through
the actual adapter, including exact-head commit retrieval and required branch
checks. Confirm installation scope and errors without printing credentials,
private response bodies or tokens. A successful health endpoint alone does not
prove GitHub access. The complete drill still needs the real task's independently
reviewed and merged PR and the public Workstream submission/contribution journey.

See the [project guide](guide.md), [drill plan](README.md), and
[shared forge boundary](../../docs/engineering/local-agent-loop.md).
