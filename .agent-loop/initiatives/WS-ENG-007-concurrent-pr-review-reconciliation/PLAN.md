# Plan: WS-ENG-007 - Concurrent PR Review Reconciliation

## Approach

Implement the trust model in three ordered chunks.

First, introduce deterministic reviewed-patch and base-advance evidence. A
review is preserved only when the original PR patch can be reconstructed, the
same patch applies to new `main`, its resulting effective delta is identical,
and neither the new-base delta nor declared dependency boundaries affect the
reviewer's track. Ambiguity invalidates.

Second, add structured reviewer-track and finding reconciliation. Findings have
stable IDs, target evidence, owner track, and a machine disposition. Trusted
upstream changes may resolve a finding only when a deterministic predicate
proves the finding is absent in the combined tree. A `false` result keeps the
finding valid and reruns its owning track; `unknown` stales every track. Human
approval is never synthesized.

Third, add `merge_group` workflow support and combined-tree evidence. Only
after repository tests prove parity will a human administrator enable GitHub's
merge queue and align required checks.

## Canonical Git evidence

One shared `scripts/git_tree_evidence.py` module is the only Git tree/delta
authority. Loop-memory and review reconciliation consume it; neither may build a
second parser or use fuzzy `git apply` behavior.

Patch identity is canonical JSON (UTF-8, sorted keys, compact separators) with
repository identity, unique reviewed trusted-main base commit/tree, reviewed
head commit/tree, and raw-path-sorted records containing `path`, `operation`,
`old_mode`, `old_oid`, `new_mode`, and `new_oid`. Renames are always delete plus
add, never similarity guesses. SHA-256 covers the serialization. Object type and
mode are independently recomputed. Symlinks, executables, binary/empty blobs,
deletes, and directory/file transitions retain exact modes and OIDs. Submodules,
unsupported types, duplicate/invalid paths, multiple merge bases,
missing/pruned objects, and non-unique bases fail closed.

The candidate is built by an exact three-tree operation over reviewed base,
reviewed head, and latest trusted-main trees. Latest-main-to-candidate records
must equal the original canonical patch records exactly. Conflict, partial or
full upstream absorption, empty effective patch, changed mode/blob/result, or a
different manifest invalidates.

## Boundary and track authority

`.agent-loop/policies/review-boundaries.json` is the sole closed, versioned
boundary graph. Reconciliation derives boundaries; PR evidence only records the
derived version, digest, and result. Version drift, unknown path, unknown class,
unknown edge, cycle, ambiguous traversal, or unclassified multi-boundary impact
makes the affected set unprovable and therefore invalidates all tracks.
Targeted invalidation is permitted only when every path, class, edge, and
transitive impact is known.

Chunk 01 owns immutable Git evidence, boundary derivation, and the impacted
track set. Chunk 02 alone owns structured findings, upstream predicates, rerun
results, and final track evidence lifecycle.

The v1 minimum track map uses only exact evidence-gate names: `workflow_ci`
routes `CI integrity`, `architecture`, `senior engineering`, `security/auth`,
`QA/test`, and `test delta`; `auth_security` routes `security/auth`,
`architecture`, `senior engineering`, `QA/test`, `product/ops`, and
`test delta`; `payment_compensation` routes `security/auth`, `product/ops`,
`architecture`, `senior engineering`, `QA/test`, and `test delta`;
`database_schema` routes `architecture`, `security/auth`, `senior engineering`,
`QA/test`, `CI integrity`, `product/ops`, and `test delta`;
`shared_interface_contract` routes `architecture`, `senior engineering`,
`QA/test`, `product/ops`, `reuse/dedup`, `docs`, and `test delta`;
`generated_policy_process` routes all tracks; `product_runtime` routes
`senior engineering`,
`QA/test`, `security/auth`, `product/ops`, `architecture`, `reuse/dedup`, and
`test delta`; `tests_coverage` routes `QA/test`, `CI integrity`,
`senior engineering`, and `test delta`; `docs_only` routes `docs` and
`senior engineering`. Aliases, case changes, and unknown names fail closed.
Multi-class paths take the union; `unknown` routes all.

## Finding predicate grammar

Finding IDs are `SHA-256` over compact, sorted-key UTF-8 JSON with the literal
version `workstream-review-finding-id-v1` and exactly these immutable identity
fields: repository, initiative, chunk, canonical reviewer track, repository-
owned rule ID, and target. Target contains the raw repository path, target kind,
immutable original object identity or diagnostic key, predicate kind, and the
predicate's immutable expected value. Mutable severity, message wording,
disposition, candidate/upstream evidence, timestamps, reviewer session, and
rerun results are excluded. A duplicate digest with non-byte-identical
canonical identity payload rejects the complete evidence set as a collision;
it is never silently deduplicated. An exact duplicate canonical payload/ID is
also rejected as duplicate evidence, yielding `unknown` and all tracks stale.

Every predicate is a resolution predicate: `true` means the exact candidate
proves the finding resolved; `false` means `still_valid`. `blob_equals` is true only
for the expected blob, `blob_absent` and `path_absent` only when the bound path
is absent, `mode_equals` only for the expected mode, and `diagnostic_absent`
only when a repository-owned typed checker reports the diagnostic absent. A
`diagnostic_absent` identity additionally binds the checker repository path,
checker blob OID, declared checker version, diagnostic code, input-schema
SHA-256, and output-schema SHA-256. Evaluation records the same fields from the
checker actually loaded from the candidate tree; any identity, version, or
schema mismatch is `unknown` and invalidates all tracks.
Before evaluation, a renamed or recreated bound target is `unknown`; missing is
false for equals predicates and true only for absence predicates when identity
continuity is not ambiguous. Evaluator error, contradiction, unsupported target,
or identity ambiguity is `unknown`; every `unknown` mandates all tracks become
`track_stale`. A finding
fixed on main but reintroduced by the PR evaluates false and remains
`still_valid`. Arbitrary commands, code, expressions, regexes, URLs, comments,
and claimant-authored dispositions are forbidden.

Findings are linked only when their immutable identity payloads have the same
repository, initiative, chunk, raw target path, target kind, and original
object identity or diagnostic code key. Unlinked findings never block
one another. Linked findings are contradictory when their predicate kinds or
immutable expected values assert mutually exclusive candidate facts: distinct
`blob_equals` OIDs, distinct `mode_equals` modes, an absence predicate paired
with an equality predicate, or distinct diagnostic checker/schema identities
for the same diagnostic code. Linked-set evaluation is atomic: only an all-true,
contradiction-free set resolves every member; any `false` with no unknown or
contradiction makes every linked member `still_valid`; and any `unknown`,
contradiction, or cross-track disagreement makes every linked member `unknown`
and stales all tracks.

## Merge-queue activation checkpoint

Chunk 03 proves repository-side readiness with static and synthetic merge-group
fixtures only. GitHub cannot emit a real merge-group event before queue
enablement. After 03 merges, a separately authenticated human administrator may
enable the queue, submit two approved concurrent PRs in both orderings, verify
the exact intermediate group SHAs/trees and required contexts, and immediately
disable/roll back on any mismatch. Final trees may be identical for disjoint
changes; every intermediate base, ordered input set, group SHA/tree, and
evidence record must remain distinct. The workflow cannot enable or merge.

## Human and CI invariants

Every preserved internal track still requires fresh CI on the exact candidate
or merge-group SHA. GitHub may dismiss stale human approval after any update.
This system neither preserves nor synthesizes it, and the specific PR still
requires explicit human merge approval.

## Preservation algorithm

```text
reviewed base + reviewed PR patch -> reviewed combined tree
latest trusted main + same patch   -> candidate combined tree

if patch cannot apply, effective patch changes, boundaries overlap,
required evidence is missing, or classification is uncertain:
    invalidate affected tracks (or all tracks when impact is unknown)
else:
    preserve unaffected internal tracks

always:
    run required CI on the candidate combined tree
    retain explicit human merge approval
```

## Alternatives rejected

- Path-disjointness alone.
- Timestamp/comment-based staleness.
- Automatic AI declarations that a semantic change is harmless.
- Enabling merge queue before workflows support `merge_group`.
- Folding this work into CI-02B, whose approved scope is semantic test lanes.

## Verification strategy

- Synthetic repositories with exact tree/blob identities.
- Adversarial base advances across overlapping and indirect boundaries.
- Rebase, merge, squash-equivalent, conflict, deleted-object, and forged-record
  cases.
- Workflow assertions proving identical required checks for PR and merge group.
- Repository-side static and synthetic assertions proving two concurrent PR
  orderings preserve required-check parity. Real hosted two-ordering evidence
  is collected only at the separate post-merge human-admin activation
  checkpoint: temporarily enable the queue, verify the emitted group commits,
  trees, and contexts, and retain or immediately disable it based on results.

## Stop conditions

Stop if preservation depends on mutable PR prose, inaccessible commits, an
unbounded semantic judgment, weakened CI, or automatic human approval.

## Recovery reliability plan — WS-ENG-007-00R2

1. Replace exact-cardinality protected-check validation with a deterministic
   latest-run selector that validates all same-name candidates against exact
   head, pinned app, structural fields, and parseable timestamps before sorting.
2. Reject the complete name-set if any candidate is malformed, untrusted, or
   incomplete. Order completed candidates by parsed `started_at` instant then
   positive numeric check-run ID. `completed_at` proves terminal consistency
   but never defines invocation recency. Require the selected run to succeed.
3. Extend the closed recovery certificate with schema v3: an ordered
   `recovered_merges` list plus one activation. Validate exact plan equality,
   chronological first-parent adjacency, identities, aggregate required checks,
   protected-check provenance on every recovered/target head, uniqueness, and
   consumption. Schema v3 permits at most two recovered merges; production
   requires exactly both named entries.
4. Bind production recovery to PR #187, PR #188, and direct-next 00R2 only.
5. Prove adversarial rerun histories, permutation invariance, exact recovery,
   non-serialization, replay rejection, and deterministic repeated output.
6. Preserve the existing workflow, signing, human approval, successor stops,
   and required-check names unchanged.

Rejected alternatives: ignore duplicate runs, accept any successful run, use API
array order, use only a check name/status context, rerun until history changes,
manually edit signed state, or add a persistent recovery bypass.
