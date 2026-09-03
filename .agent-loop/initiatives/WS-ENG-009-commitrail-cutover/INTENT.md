# WS-ENG-009 Intent — Commitrail Cutover

## Problem being solved

Workstream's repository-native engineering method has accumulated a large
`.agent-loop` implementation whose duplicated state, historical queues,
merge-intent records, and mandatory projections can confuse contributors and
create process work unrelated to the change being delivered. Commitrail v0.1
captures the useful controls in a smaller portable method.

## Why this work matters

Workstream must be the first complete real-world proving ground for Commitrail.
The repository should preserve intent, boundaries, evidence, exact-target
review, and human merge authority without maintaining a second authorization
system or a stale shadow of GitHub.

## Current behavior

`.agent-loop` contains current navigation, policies, templates, initiative
plans, reviews, and retired automation records. Repository instructions,
skills, reviewer definitions, CI, scripts, tests, and some canonical product
documents refer to it directly.

## Target behavior

`.commitrail` is the only active engineering-record location. A meaningful
single-PR change normally uses one combined change record. Multi-PR work uses
one initiative overview and one change record per PR. GitHub owns transient
work, checks, approvals, and merge state. Historical `.agent-loop` content is
removed from the working tree after current truth and still-normative material
are deliberately migrated; Git history remains the archive.

## Design chosen

Use one atomic cutover PR, followed by one blind stress-test PR on real
Workstream work. The cutover updates the records, contributor guidance,
skills, reviewers, automation, tests, and every live reference together. It
does not run two active methods in parallel.

## Alternatives considered

- A directory rename was rejected because it would preserve the accumulated
  complexity under a new name.
- A prolonged dual-read period was rejected because it would create two
  apparent sources of engineering truth.
- Deleting all records without classification was rejected because a small
  number of current handoffs, decisions, and constraints are cited by current
  specifications.

## Boundaries preserved

- GitHub permissions and branch protection remain authoritative.
- Human maintainers retain merge and material-risk decisions.
- Product lifecycle terminology and behavior do not change.
- Existing test and coverage protections may not be weakened.
- Other worktrees are not edited by this initiative.

## Expected risks

- A hidden `.agent-loop` dependency may break CI or contributor tooling.
- Removing a cited record may erase context still needed by a canonical spec.
- Active branches may carry old paths and require rebase reconciliation.
- Commitrail could accidentally reproduce the same ceremonial complexity.

## What must not change

No backend, frontend, database, API, authorization, artifact, review,
contribution, compensation, or product behavior may change during cutover.

## How this will be proven

The cutover must pass reference scans, Markdown links, focused script tests,
all Agent Gates, applicable reviewer tracks, and a repository-wide assertion
that `.agent-loop` is absent and no active instruction references it. The next
real bounded Workstream change must then complete entirely through Commitrail
without compatibility files or manual state repair.

## Human decisions required

Approve the atomic-cutover boundary and selection of the first real stress-test
change. Human approval is also required before either PR is merged.
