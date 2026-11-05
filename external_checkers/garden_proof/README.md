# Garden engineering proof image

Build the offline image from the shared evaluator and Garden-owned entry point:

```sh
docker build -f external_checkers/garden_proof/Dockerfile -t ws-garden-proof:qualification external_checkers
```

One image registers `garden.work_proof` version `v1` separately for `pre_submit`
and `post_submit`. Use its exact platform-manifest digest. A changed image needs
a new capability version and explicit registration; retained evidence is not
rewritten. The existing Harnessy image now uses capability version `v4` for the
expanded exact forge-facts shape. Old pinned images have no fallback parser.

`publish_local.py` reuses the existing loopback-only image publisher and emits
`checker-service.json`, `registry-pre.json`, and `registry-post.json`. It requires
`--registry`, `--compose-project`, `--sandbox-uid`, `--sandbox-gid`, `--out-dir`;
`--capability-version` defaults to `v1`. Running it builds and publishes locally.
No image is published merely by adding these sources.

PRE configuration is exactly:

```json
{"repository":"Flow-Research/garden","forge_origin":"https://github.com"}
```

PRE checks root `proof.json` as bounded UTF-8 JSON and validates existing
`harnessy.work.proof.v1` schema, landed-SHA shape, successful CI/merged claims,
and canonical Garden PR and Actions-run URLs. It has no forge facts or network.
Passing intake creates no acceptance evidence about the external work.

POST configuration selects the existing scoped forge capability:

```json
{"workstream_forge_facts_version":"v1","forge":"github","forge_origin":"https://github.com","repository":"Flow-Research/garden","base_branch":"main"}
```

POST reuses Harnessy's merge, landed commit, repository/base, CI producer,
independent current-head human review, and protected-path rules. Its offline
locator reuses the bounded root proof parser; shared POST interprets no Garden
format. Workstream supplies the reviewed PR head's immutable `head_commit_message`
and its response hash through the existing forge-facts adapter. The GitHub App
needs repository Contents read permission for the commit-object endpoint, in
addition to existing proof-facts permissions. The response is streamed with a
256 KiB cap and the message is limited to 64 KiB of UTF-8; oversized or malformed
responses are infrastructure protocol failures, never truncated claims.

The head message must contain exactly one reserved `Workstream-Task` occurrence
(case-insensitive duplicate detection), as this exact line in its final trailer
block, with canonical lowercase UUID spelling:

```text
Workstream-Task: <trusted Workstream task UUID>
```

The image compares it with Workstream's trusted `input.task_id`. Add the trailer
before final checks and review: changing it changes the head SHA. Findings are
`garden.proof.task_trailer`, `garden.proof.task_mismatch` or
`garden.proof.task_identity`; existing `harnessy.proof.*` findings retain their
meaning. Canonical URL/configuration findings use `garden.proof.pr_url`,
`garden.proof.ci_run_url` and `garden.proof.configuration`.

This proves declared reviewed task association. It does not link GitHub accounts
to Workstream contributor identities. The Workstream submitter remains
accountable; independent GitHub review is checked against the GitHub author.

Qualify the actual offline image through the native service using controlled
facts (this is not a live GitHub read or durable public-API drill):

```sh
backend/.venv/bin/python external_checkers/workstream-checker-service/tests/harnessy_forge_composition.py --service external_checkers/target/debug/workstream-checker-service --checker-image ws-garden-proof:qualification --garden-proof
```
