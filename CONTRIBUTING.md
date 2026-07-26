# Contributing To Workstream

Workstream welcomes repository contributions from humans and agents. A
**repository contributor** proposes changes to this GitHub repository. A
Workstream product **Contributor** is an actor in the task, submission,
contribution-record, compensation, and reputation lifecycle. Repository access
does not grant product authority, and product status does not grant repository
authority.

## Why The Engineering Loop Is Strict

Workstream coordinates human-agent work by binding intent, scope, evidence,
review, and human accountability. Repository changes use the same principles so
that reviewers can understand what was authorized, distinguish independently
verified proof from claims, and recover the exact state after concurrent work.
The controls apply equally to maintainers, other humans, and agents.

The canonical engineering loop is:

```text
Intent -> Discovery -> Plan -> Chunk Map -> Chunk Contract -> Implementation -> Evidence -> Internal Review -> PR -> Human Checkpoint -> Automated Merge Memory -> Stop
```

Each initiative may have at most one active planning or implementation chunk.
Distinct initiatives may run concurrently. Branches and worktrees isolate
execution; they are not authority.

## Before Work

1. Read [AGENTS.md](AGENTS.md), the
   [repository engineering policy](.agent-loop/policies/repository-engineering-policy.md),
   and the [agent-loop guide](.agent-loop/README.md).
2. Find the smallest applicable reviewed artifact: an initiative plan for
   large or ambiguous work, or a bounded chunk contract for smaller work. The
   contract must state allowed files, forbidden changes, acceptance criteria,
   risk, verification commands, reviewers, and human review focus.
   Post-cutover implementation and specification contracts also carry one
   strict `chunk-scope-json` block. Agent Gates compare the complete PR and
   local-status delta with that block; prose cannot widen it.
3. Ask an authenticated repository writer to dispatch `Loop Memory Explicit
   Event` on exact current `main`. A valid start is independently verified
   signed state on `automation/loop-memory`; chat, an issue, a branch, a commit,
   a fork, a pull request, or a local worktree is never canonical authority.
   Only independently verified signed automation state is canonical authority.
4. Confirm the target initiative is active for the exact chunk and phase before
   implementation. The signed start is the single authorization checkpoint; an
   orchestrator does not request a second approval after an explicit start
   instruction.

A new initiative that is absent from signed history first uses the closed
planning-only intake described in the [agent-loop guide](.agent-loop/README.md#first-planning-intake).
That merge publishes reviewed planning and a successor contract but leaves the
initiative stopped. It never authorizes implementation.

## Contributors Without Write Permission

Use a public [GitHub issue](https://github.com/Flow-Research/workstream/issues/new)
to request planning or propose an existing patch. Include the goal, rationale,
known files and tests, risks, and a link to any fork commit or patch. Do not
publish unsigned implementation as a Workstream implementation PR.

A maintainer adopts the request by:

1. preserving the proposal as discovery input and assessing its initiative and
   risk;
2. placing the required intent, discovery, plan, chunk map, and exact chunk
   contract on trusted `main` through the normal reviewed planning path;
3. dispatching the signed start for that exact contract and current-main SHA;
4. applying or recreating only the in-contract parts of the preserved patch,
   then running the complete evidence and review loop; and
5. crediting the original contributor in the resulting PR where applicable.

An existing commit or patch is preservation and discovery input only. It is
never retroactive authorization, evidence that the chunk started, or a reason
to skip current-main reconciliation, tests, internal review, or human approval.

## Implementation

- Work in the exact signed chunk and remain inside its allowed files and
  acceptance criteria.
- Machine scope paths are repository-relative NFC UTF-8 names. A literal file
  names one file; a trailing `/**` names that directory recursively. Absolute
  paths, `.`/`..` components, shell/regex syntax, negation, braces, backslashes,
  controls, symlinks, gitlinks, executable changes, and byte, normalization, or
  casefold collisions fail closed. A forbidden match always overrides an
  allowed match.
- Contract verification values are closed repository-owned command identifiers,
  never executable text supplied by the contract.
- Reconcile with current `main` before publication. If the base changes, inspect
  the delta and rerun all contract proof; a rebase does not replace the signed
  contract or authorize scope drift.
- Preserve tests, coverage floors, lint, type checks, security defaults, and
  workflow protections. Stop if passing requires weakening a gate.
- Record commands, results, risks, decisions, and required internal reviewer
  findings in the initiative evidence.
- Do not begin another chunk automatically. Distinct initiatives may proceed in
  parallel only when each has its own valid signed active chunk.

The scope ratchet begins when trusted `main` contains the
`WS-ENG-008-01` merge intent. Every implementation or specification start from
that point requires schema v1. Only a chunk already signed-active at the exact
cutover may finish without it, and only through generated evidence bound to its
pre-cutover start event, initiative/chunk identity, contract path, and contract
blob. Stopped, proposed, cancelled/restarted, and newly started work is never
grandfathered.

## Before Opening A Pull Request

1. Complete every required internal reviewer track and resolve or document each
   valid finding. CodeRabbit, GitHub checks, and human PR comments supplement
   internal review; they do not replace it.
2. Ensure the reviewed implementation SHA and signed-start provenance are
   recorded in the PR trust bundle.
3. Add exactly one schema-v2 merge intent for this chunk. A successor may only
   be in the same initiative; use `null` when none is declared.
4. Run the chunk's complete verification commands against the current base.
5. Open the PR only after the evidence gate passes and no reviewer agent remains
   active.

## Review, Merge, And Stop

The human owner reviews the final exact PR head, checks the trust bundle and
external findings, and explicitly decides whether that specific PR may merge.
No agent or automation may infer merge approval.

After merge, the trusted `Loop Memory` workflow generates and signs canonical
state on `automation/loop-memory`. Verify its manifest, signature, ledger, loop
view, queue, and initiative projections together. When it succeeds, do not open
a manual post-merge memory PR or repeat reviewer fanout merely to restate the
merge. Work stops. A successor starts only through a new explicit signed event;
Automated Merge Memory never starts it automatically.

For operations and recovery, follow the
[post-merge memory runbook](docs/operations_post_merge_memory.md).
