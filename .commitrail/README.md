# Commitrail in Workstream

Commitrail is Workstream's repository-native engineering method. It preserves
useful intent, boundaries, evidence, review findings, and decisions without
becoming a permission system or a stale copy of GitHub.

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> PR -> Human Merge
```

## Sources of authority

1. Code, migrations, tests, accepted ADRs, and canonical specifications define
   implemented and required product behavior.
2. [`docs/roadmap_status.md`](../docs/roadmap_status.md) is the current product
   capability ledger.
3. [Open pull requests](https://github.com/Flow-Research/workstream/pulls), CI,
   reviews, approvals, and merge state live on GitHub.
4. [`INDEX.md`](INDEX.md) records durable engineering dispositions and links to
   concise multi-PR initiative context.

Commitrail records explain work. GitHub permissions and branch protection
govern contribution authority. Humans decide product intent, material risk,
approval, and merge.

## Smallest useful record

| Change | Record |
|---|---|
| Obvious low-risk correction | PR description only |
| Meaningful single-PR change | One file based on `CHANGE_TEMPLATE.md` |
| Multi-PR initiative | One initiative `OVERVIEW.md` plus one change record per PR |
| Exceptional risk | Add only evidence or decisions needed to control that risk |

Do not commit transient labels such as “in review,” “CI pending,” or “ready to
merge.” GitHub already owns those facts. Durable dispositions are `Planned`,
`Complete`, `Stopped`, and `Superseded`.

## Starting work

1. Pull current `main` and read `CONTRIBUTING.md`.
2. Check the capability ledger, this index, canonical specifications, and open
   PRs for overlap.
3. Confirm intent and non-goals.
4. Use the smallest record above.
5. Implement, test, run impact-routed review, reconcile with current `main`,
   and open a PR.
6. Stop for human approval and merge.

Distinct initiatives may proceed concurrently. A new base invalidates only the
evidence affected by its changed impact cone.

## Exact pre-cutover work records

Every active initiative carried into Commitrail retains a verbatim
`pre-cutover/` copy of its former status, chunk map, intent, discovery, plan,
decisions, risks, chunk contracts, evidence, reviews, and other initiative
files. This preserves the complete accounting of delivered, current, blocked,
superseded, and remaining work without summarizing it away.

These exact files are handoff evidence, not an executable queue, permission
source, or instruction to repeat the former automation. Each initiative's
`OVERVIEW.md` remains the current entry point and links to its full record.
[`PRE_CUTOVER_MANIFEST.tsv`](initiatives/WS-ENG-009/PRE_CUTOVER_MANIFEST.tsv)
binds every preserved source and destination to its Git blob at the declared
cutover base. Agent Gates rejects a missing, extra, or modified preserved file;
corrections belong in current Commitrail records rather than edits to history.
