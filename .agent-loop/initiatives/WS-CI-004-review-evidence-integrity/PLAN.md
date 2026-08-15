# Plan: WS-CI-004 Review Evidence Integrity

## Proposed approach

Build a small evidence layer around the existing simple loop. The layer has four
independent concepts:

1. **Review subject:** exact base, merge base, and reviewed head.
2. **Review predicate:** specialty, scope inspected, evidence observed, findings,
   and uncertainty.
3. **Freshness:** whether relevant changes occurred after the review.
4. **Human decision:** GitHub approval and merge remain outside the internal
   attestation.

These concepts must not be combined with implementation authorization, active
initiative state, signed starts, merge memory, or successor dispatch.

## Design chosen

### Shared Reviewer Evidence Protocol

Add one mandatory repository skill used by every custom reviewer. It requires:

- base SHA, merge-base SHA, start head, end head, and worktree state;
- exact diff range and relevant unchanged implementation inspected;
- contract/current-state/policy/ADR/ownership/debt-ledger sources consulted;
- evidence executed versus evidence merely inspected;
- prior finding IDs and their final-head dispositions;
- canonical subsystem owner and cross-module public-boundary checks;
- explicit uncertainties and unavailable proof;
- a verdict that is invalid if the head changes during review.

Specialty skills add domain questions; they do not duplicate the shared protocol.

### Reviewer effectiveness, not prompt presence

Every custom reviewer agent and its matching repository skill receives an
explicit responsibility contract in `REVIEWER_MATRIX.md`. Adoption is not
complete merely because all prompts reference the shared protocol. Each reviewer
must pass isolated forward evaluations using raw diffs and repository evidence:

- a positive fixture containing a defect the specialty must find;
- a negative fixture it must not misclassify;
- a stale-head or prior-finding replay fixture;
- an output-contract fixture proving exact target, evidence, finding IDs,
  uncertainty, and disposition are present;
- a cross-specialty handoff fixture when the finding belongs to another owner.

Evaluation prompts must not leak the intended answer. A reviewer that repeatedly
misses its owned failure class is not considered adopted, even if its wording is
complete.

### Deterministic target inspection

Add one small read-only Python command that resolves and emits a machine-readable
review target:

```text
base ref and SHA
merge-base SHA
head SHA
tracked/staged/unstaged/untracked state
changed paths and statuses
```

It does not decide reviewer results, authorize work, update state, or call an
external service. Reviewers run it at start and again before verdict.

### Finding replay

Reviewer findings use stable IDs within one PR review chain. Each record includes
source head, severity, location, problem, disposition, fix commit when any,
verification, and final-head replay status. Critical/High remain blocking;
Medium requires a human decision; Low/Informational remain visible.

Internal reviewer receipts are advisory session evidence, not canonical durable
repository records. During one orchestration run, the orchestrator is the only
writer and stores validated JSON receipts outside the worktree at:

```text
$(git rev-parse --git-common-dir)/workstream-review/
  <pr-or-branch>/<base_sha>-<merge_base_sha>-<head_sha>/<run_id>/<specialty>.json
```

The orchestrator never uses a raw PR or branch identifier as a path component.
A pull request key is `pr-` plus its canonical unsigned decimal number. A branch
key is `branch-<byte-length>-<base64url>`, where the payload is the unpadded
base64url encoding of the branch name's NFC-normalized UTF-8 bytes. This mapping
is injective over normalized identifiers; canonically equivalent Unicode names
intentionally share one identity. Empty, invalid UTF-8, NUL, and control-bearing
identifiers are rejected. The encoded component must contain no path separator,
must not be `.` or `..`, and its resolved target must remain beneath the resolved
receipt root with no symlink component.

The orchestrator creates directories and files with user-only permissions and
writes each receipt atomically with create-without-overwrite semantics. Reviewer
agents return structured output but cannot designate a receipt as accepted.
A push or base change creates a new target directory; it never edits the previous
receipt. Stable finding IDs are copied into the new session and explicitly
closed, accepted, or left blocking. The first implementation step must extend
the existing evidence and finding templates and add an adjacent canonical JSON
receipt schema before any receipt writer or convergence reader is implemented.
PR summaries may mirror that schema but are not receipt custody.

This storage proves session consistency, not independent reviewer identity or
long-term attestation: the orchestrator and reviewer processes share one local
OS trust boundary. GitHub check runs, submitted GitHub reviews, branch
protection, and merged Git history remain the durable repository evidence.

### Final review-target barrier

Only a clean worktree may produce a final reviewer verdict or converged receipt.
Dirty tracked, staged, unstaged, or untracked state may produce provisional
findings, but never `PASS` or merge-readiness evidence. The target tool checks
cleanliness at reviewer start and immediately before verdict. A local change
after reviewer start invalidates the run even when all three SHAs are unchanged.

After any push, deterministic evidence is refreshed. Reviewers are rerun when
the delta intersects their files, boundaries, findings, or evidence claims. The
orchestrator fetches the PR head again after all required reviewers finish and
must not report readiness unless every applicable session receipt converges on
the same `{base_sha, merge_base_sha, head_sha}` review target. Hosted GitHub
checks bind natively to the same `head_sha`; the orchestrator resolves their base
and merge base for the current session instead of pretending GitHub supplied
fields it does not expose. A base change is evidence drift even when the head
SHA is unchanged.

GitHub's stale-approval/last-push protection remains the authoritative human
counterpart.

### No hosted receipt validator in this initiative

This initiative does not create a hosted receipt store, trusted issuer, receipt
workflow, or blocking evidence gate. A future proposal may consider durable
attestation only after its custody and issuer threat model is independently
designed and approved. It cannot be inferred from these session receipts.

## Threat model

The protocol must detect or expose:

- a pass copied from an older commit;
- a branch update after review;
- a base update changing the effective diff;
- dirty local state excluded from the claimed review;
- a trust bundle claiming an unexecuted or failed command passed;
- a reviewer checking only changed lines and missing a relevant existing
  consumer, owner, import, debt ledger, or historical contract;
- a prior finding silently disappearing;
- one reviewer passing a different head from the other reviewers or CI;
- session evidence being mistaken for durable GitHub evidence.

It does not claim to detect reviewer collusion, malicious GitHub administrators,
or every semantic defect. Human judgment and independent sensors remain required.

## Alternatives rejected

- Restore the old monolithic gate.
- Use mutable prose without exact revision identity.
- Require all nine reviewers after every push.
- Store active review state as repository memory.
- Let reviewer evidence authorize implementation or merge.
- Invent a hosted receipt validator before custody and issuer trust exist.
- Add cryptographic signing before ordinary Git/GitHub identity is proven
  insufficient.

## Boundaries preserved

- Product/runtime: unchanged.
- Auth/payment/data: unchanged.
- CI: only additive measured checks; no existing check or threshold weakened.
- Contribution authority: GitHub permissions and branch protection only.
- Merge authority: explicit human approval only.
- Engineering state: initiative records describe plans and outcomes, never locks.

## Verification strategy

- Unit fixtures for clean, dirty, divergent, rebased, renamed, deleted, and
  untracked Git states.
- Golden output tests for every reviewer receipt field.
- Per-reviewer effectiveness fixtures defined in `REVIEWER_MATRIX.md`, including
  both required detections and false-positive controls.
- Negative prompt-contract tests for missing SHA, missing replay, unsupported
  evidence claims, and unknown Medium disposition.
- PR #338 replay fixtures covering all five missed defects.
- Tests that unrelated documentation-only receipt changes do not trigger
  unrelated specialty reruns.
- Tests that affected implementation, contract, policy, test, workflow, and
  ledger changes do invalidate the correct specialties.
- A pure convergence validator proving all required receipts and checks refer
  to one `{base_sha, merge_base_sha, head_sha}` triple.
- Named regression fixtures for the five PR #338 misses: contract-path
  continuity, atomic outcome vocabulary, owner/public-port boundaries,
  completed-history immutability, and machine/human debt-ledger parity.
- Receipt-custody tests proving private out-of-tree location, create-once writes,
  target-scoped supersession, and explicit prior-finding replay.
- Identifier tests covering traversal text, slash and backslash input, Unicode
  normalization, normalized aliases, distinct-identifier non-collision, symlink
  escape, and resolved-root containment.
- A regression fixture proving a local change after reviewer start prevents a
  final verdict despite an unchanged SHA triple.

## Review strategy

Every future implementation step is L1/P1 engineering-loop infrastructure.
Required reviewers are
architecture, CI integrity, security, QA/test, senior engineering, docs,
reuse/dedup, and test delta when tests change. Product/operations confirms that
engineering review language never leaks into Workstream product review decisions.

## Rollout and rollback

The shared protocol and target tool land first and must reuse
`scripts/git_delta.py` rather than create another Git-resolution helper.
Reviewer adoption and local session convergence follow only when explicitly
started. Their contracts must name exact implementation, test, and fixture paths
plus runnable commands. If the protocol is noisy, amend it directly in a bounded
reviewed change; do not add hosted custody, bypass CI, or weaken human approval.
