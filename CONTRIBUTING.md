# Contributing To Workstream

Workstream welcomes contributions from humans and agents. Repository access is
governed by GitHub permissions and branch protection. The engineering loop
exists to make work understandable and reviewable; it is not a separate
authorization system.

Workstream itself is source-agnostic governed contribution infrastructure. Flow
Identity is its current v0.1 external authentication provider, not its product
owner or repository contribution authority. Read the complete product boundary
in [README.md](README.md) before changing product terminology or architecture.

## Simple Engineering Loop

```text
Intent -> Plan -> Bounded Change -> Tests -> Review -> Pull Request -> Human Merge
```

## Set Up The Development Environment

Use the [Developer Quickstart](README.md#developer-quickstart) before running
repository checks. Docker is the supported cross-host path for macOS and
Windows and selects native Linux x86_64 or aarch64 inside the Docker VM. Native
host setup is supported only on the Linux/glibc/Python matrix documented there.
Do not replace the approved Pillow artifacts to make an unsupported host install
pass.

Repository engineering checks use a separate, hash-pinned tooling environment,
not the backend environment. The tested local tooling setup is Linux x86_64,
CPython 3.12, Git, and uv (see the native quickstart for uv installation).
From the repository root, install it with:

```bash
uv venv .venv --python python3
uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: \
  -r .github/requirements/agent-gates.txt
```

The root `.venv/` is ignored and separate from `backend/.venv/`. If you already
use that path for another environment, choose another unused path and use its
Python consistently below.

Other hosts use the required hosted Agent Gates check on the pull request.
The backend Docker service mounts only `backend/`; it is not a repository-root
tooling environment. Do not change dependency hashes to force a host install.

For an obvious low-risk correction, record intent and scope in the pull
request. A meaningful implementation change uses one record based on
`.commitrail/CHANGE_TEMPLATE.md`. Multi-PR work also uses one concise initiative
overview. Commitrail records are useful context, not runtime locks or
permission to contribute.

## Find The Current Contract

Before implementation, update from current `main` and read:

1. [README.md](README.md) for the product boundary and current v0.1 summary.
2. [v0.1 Roadmap And Capability Status](docs/roadmap_status.md) for implemented,
   hidden, in-progress, and remaining capabilities.
3. [Commitrail Engineering Index](.commitrail/INDEX.md) for durable
   initiative dispositions and remaining boundaries. Inspect GitHub separately
   for the live pull-request view of transient work.
4. [Architecture Lockdown](docs/architecture_lockdown.md), accepted ADRs, and
   the canonical specification for the subsystem being changed.

Code, migrations, tests, accepted ADRs, and canonical repository specifications
define implemented or required behavior. Open pull requests describe work in
progress. Calendar plans, early chunk specifications, imported files under
`docs/reference_specs/`, internal review records, and closed initiative records
are useful history unless a current document explicitly adopts them; they are
not by themselves current sequencing or proof that behavior is live.

The active migration graph is the clean v0.1 baseline. A local database with a
removed pre-v0.1 revision must be recreated; do not add a compatibility stamp,
bridge migration, or second baseline.

Roadmaps and status documents must use capability milestones and evidence. Do
not introduce delivery promises such as day plans, numbered weeks, or rolling
time windows as repository authority.

Contributors with GitHub write access may create a branch, implement a bounded
change, and open a pull request. Contributors without write access may use a
fork and open a normal pull request.

Before claiming a remaining boundary, inspect
[open pull requests](https://github.com/Flow-Research/workstream/pulls) and
coordinate any overlapping path or behavior ownership. Static status files do
not attempt to mirror transient branches because that information becomes
stale at merge. Review logs are evidence for earlier exact changes, never an
active queue or approval gate.

## Before Opening A Pull Request

- Explain the goal, scope, non-goals, and important design decisions.
- Keep the change small enough to review.
- Run the relevant tests, lint, type checks, and coverage checks.
- Preserve security defaults and existing coverage floors.
- Record important reviewer findings and how they were resolved.
- Reconcile with current `main` and rerun affected checks.
- In the change record, declare the intended merge outcome and durable
  disposition (`Planned`, `Complete`, `Stopped`, or `Superseded`). Update an
  initiative overview or index row only when its durable meaning changes.
  Never commit transient review or CI state, and never create a second
  post-merge memory PR.

Commit/freeze the candidate. With the local tooling setup above, run the same
atomic check before pushing; other hosts inspect the required hosted result.
Its base-to-HEAD comparison does not validate uncommitted edits:

```bash
.venv/bin/python scripts/check_commitrail_records.py --base-ref origin/main
```

Security, authorization, payments, workflow, architecture, and other high-risk
changes require focused internal review before they are ready to merge. Small
low-risk changes use proportionate review. Reviews are evidence, not permission
to contribute.

## Review And Merge

GitHub CI validates repository quality. CodeRabbit and internal agents
supplement human review. A maintainer must explicitly approve the final pull
request before it is merged, and the user must explicitly approve that specific
pull request for merge. A new push invalidates affected internal evidence and
stale GitHub approval. Branch protection requires an eligible human other
than the latest pusher to approve the most recent reviewable push, and requires
all review conversations to be resolved before merge.

Different initiatives may proceed concurrently in separate branches or
worktrees. If another pull request changes the base, inspect the new delta and
rerun affected checks; unchanged evidence does not need ceremonial repetition.

## Behavior Ownership Catalogue

The hosted behavior-mutation check is temporarily retired because its
callable-wide survivor policy blocked declaration-only changes by mutating
unchanged executable lines. Do not treat a historical behavior claim or a
catalogue candidate as a required PR gate.

The versioned catalogue foundation lives under `.ci/behavior-ownership/`.
Contributors can run its read-only inventory, candidate generator, and validator
from `backend/`:

```bash
.venv/bin/python -m scripts.behavior_ownership inventory
.venv/bin/python -m scripts.behavior_ownership generate
.venv/bin/python -m scripts.behavior_ownership validate
```

Candidate output is discovery assistance only. It cannot become reviewed
ownership without an explicit catalogue record and the required human and
internal review. The validator reports unresolved targets while population is
in progress; that report does not block ordinary contributions.

Existing claim, schema, policy, dependency, and evidence files remain as
historical design input. They do not replace focused tests, hosted Backend
lanes, coverage floors, internal review, CodeRabbit, or human merge approval.
Behavior-mutation enforcement must not resume until a fresh changed-line-aware
plan is approved and proves that unchanged executable lines cannot block a
declaration-only change.

## Durable Records

Keep only Commitrail records that materially explain intent, boundaries,
decisions, evidence, or remaining risks. Git history preserves retired detail.
Git and GitHub are authoritative for commits, reviews, checks, approvals, and
merges.
