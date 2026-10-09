# [PILOT-14] — Show locked task compensation before claiming

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Authorized project Submitters and Reviewers see exact compensation terms from each task's locked ContributionPolicyVersion in ready-work and contributor task-detail reads.

## Intent

Let a contributor evaluate a task's compensation before claiming it without
granting Finance-policy access or resolving the project's current policy.

## Current behavior

`ReadyTaskSummary` and `ContributorTaskDetail` omit compensation. TASK stores
`locked_contribution_policy_version_id` when screening a task, while the
Finance-authorized ContributionPolicy read exposes internal identifiers that
must not cross a contributor response. `task.queue.read` and `task.read`
currently accept only an active exact-project Submitter grant.

## Bounded change

### Allowed

- CONTRIBUTIONS public locked-terms contracts and their owner repository/adapter.
- TASK ready queue and contributor detail contracts, projections, composition,
  and existing AUTH read guards for active exact-project Submitter or Reviewer
  grants.
- CLI `task ready` and `task show` response validation and text display.
- Focused real-PostgreSQL and CLI HTTP process proof, current API/CLI,
  authorization, compensation and roadmap documentation, required test-lane
  catalogue registration, and this record.
- The existing nine-lane runner/catalogue, focused CI contract tests and backend
  testing operations guide needed to keep the exact full inventory within the
  unchanged hosted execution deadline.

### Not allowed

- Policy creation, locking, publication, retirement, payment, award creation,
  fulfillment, adapter-binding behavior, route keys or binding status.
- Migrations, task-specific term editing, Finance read access, new permissions,
  lifecycle states, parallel owner implementations, or private cross-owner imports.
- Test deletion or skipping, a timeout or lane-count increase, weaker evidence
  custody, fake service substitution, or a product-source workaround for CI cost.
- PILOT-13 guide-read implementation, PR #504 dispatch work, deployment, merge,
  issue closure, or another implementation chunk.

## Design and decisions

CONTRIBUTIONS exposes one bounded public read port that projects only a locked
version UUID and the two complete contribution rules. Each rule is either the
literal `unpaid` or an immutable award list containing only `instrument`,
`unit`, and exact decimal-string `quantity`. TASK supplies only the version UUID
stored on each task and embeds the detached result in ready/detail responses.
The existing ready/detail authority paths accept either active exact-project
contributor role; claim/start and other Submitter operations remain unchanged.

PR #505 overlapped TASK command/router schemas, CLI client/docs and roadmap files.
This change was implemented independently, then rebased onto its merged head.
The reconciliation preserves guide-document fields, delivery authority and CLI
validation alongside compensation, and adds no migration.

## Acceptance criteria

- [x] Unpaid locked rules show `unpaid` for both contribution types in ready and detail responses.
- [x] Paid manual-export fixtures show each exact instrument, unit and decimal-string quantity.
- [x] Publishing a successor policy cannot move an already-released task's displayed terms.
- [x] Active exact-project Submitters and Reviewers see identical terms; absent, revoked and foreign-project roles receive the existing concealed response.
- [x] Responses and CLI output contain no adapter binding ID, route key, binding status, policy lifecycle status or other Finance internals.
- [x] CLI `task ready` and `task show` validate and display the block through public HTTP.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, QA, test delta, reuse/dedup, documentation, ci_integrity
- Human review focus: locked-version lineage, exact-role concealment, exact decimals,
  the narrow cross-owner projection, and exact CI assignment/evidence custody with
  measured deadline headroom.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Locked compensation is exact and concealed | Isolated real-PostgreSQL locked terms, ready/detail/work-context/public-queue and changed AUTH matrix tests | Passed at `ec4c8505` after PR #509 reconciliation: 2 locked-term cases; the retained product source previously passed 60 owner projection cases and 7 matrix cases. Hosted Backend run `37906026854` at `8363c0e0` passed all nine lanes and the canonical aggregate across 8,805 nodes | None. |
| CLI validates and renders public output | Built CLI HTTP process tests plus `go test ./...`, `go vet ./...`, `go mod verify` and build | Passed at `677101a8`: 12 process cases and all Go checks; PILOT-14 receipt/rendering behavior and process tests are retained, while current CLI compilation and `task ready --help` passed after reconciliation | None. |
| Repository contracts remain consistent | Lane-catalogue and architecture/module-boundary tests, Ruff and compile checks | Passed at `ec4c8505`: 81 catalogue/boundary cases. After the measured lane repair, 62 focused catalogue/runner cases, Ruff, Markdown links, stale wording and Commitrail checks pass; compensation source and tests remain unchanged | Fresh exact-head hosted CI remains external evidence. |

## Review findings

The architecture check found that the first TASK response contract directly
referenced the CONTRIBUTIONS result type. TASK now owns its immutable response
DTO and maps from the existing CONTRIBUTIONS public port in repository
composition; the full module-boundary suite passes. Remaining exact-head
impact-routed review is coordinated by the lead.

The first current-main hosted run at `ff62b273` used the predecessor CI lane
allocation. TASK B completed 404 of 411 collected nodes before the unchanged
1,200-second deadline, with no assertion failure and complete PostgreSQL/MinIO
cleanup; all other lanes and the CLI contract passed. Merged PR #515 moves the
measured checker workload out of TASK B while preserving the canonical inventory.
Fresh hosted evidence at `8363c0e0` passed all nine lanes and the canonical
8,805-node aggregate. TASK B completed all 380 selected nodes in 731.367 seconds
with zero skips or deselections and complete PostgreSQL/MinIO cleanup. The later
roadmap-only correction keeps PILOT-14 in open status until human merge; product
source and test blobs remain unchanged, while the documentation head requires
its own hosted checks.

That documentation head exposed a separate measured project-lane imbalance.
Hosted run `37909246303` passed Agent Gates, MCP, preflight, MinIO, CLI and eight
of nine lanes, while project B completed 729 of 761 nodes before the unchanged
1,200-second deadline. It reported no assertion failure, skip or deselection;
PostgreSQL and MinIO cleanup completed, and the aggregate correctly rejected the
interrupted lane. The immutable lane artifact is `11606463730`.

The first proposed repair, assigning both broad PROJECT modules solely to
project A, was rejected from retained measurements: project A took 951.944
seconds, project C took 745.983 seconds, and the modules' retained B/C phases
would have projected project A to at least 1,189.274 seconds before hidden phases
or runner variance. The reviewed shared repair from `6256f239` instead excludes
those modules from project B and partitions their exact nodes across project A
and C with the existing hash. It preserves nine lanes, the 1,200-second deadline,
all canonical nodes, real PostgreSQL/MinIO execution and authenticated evidence;
the bounded logs retain only the 25 slowest phases. Replaying the failed run's
8,805-node manifest through the repaired catalogue retained every unique node
exactly once: 304 nodes from the two measured modules split 155 to project A and
149 to project C, with none left in project B. This PR applies only the five shared
runner, catalogue, focused-test and operations-guide files, preserving its
PILOT-14 catalogue entries and all compensation product source and tests.

## Reconciliation

- Current-source reconciliation: Merged `main` at `77d6db61`, preserving PR #504
  submission dispatch, PR #505 guide-document contracts, PR #509 hidden
  evaluation-request delivery, PR #507's qualified gVisor experiment limits,
  PR #513's guide upload and PR #515's measured CI allocation alongside
  compensation and their current owner inventories.
- Next usable boundary: Human merge of this bounded PR; payment and fulfillment remain separate work.
- Remaining risks: None beyond independent review and hosted CI.
