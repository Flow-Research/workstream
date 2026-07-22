# PR Trust Bundle: WS-REV-001-PLAN3

## Chunk

`WS-REV-001-PLAN3` - Allow-Review Boundary Reset.

## Goal and human-approved intent

Restore the strict REV boundary: begin at durable final/current `allow_review`,
consume the finalized Submission and its same submitted/verified artifacts,
and never implement upstream owner gaps.

## What and why

The prior 02A/02B/02C plan crossed into Project Guide, Task intake, Submission,
and checker ownership. This candidate reverts the attempted runtime change,
retires those contracts, records immutable Submission/Review lineage and exact
contribution cardinality, and proposes bounded successors 03P then 03A.

## Design and scope control

- 03P owns only immutable REV ReviewPolicy/RevisionPolicy persistence.
- 03A owns only queue/lease persistence and linkage.
- Atomic `allow_review` admission remains later in 05A.
- Upstream gaps are typed owner blockers, never opportunistic REV repairs.
- Adjudication consumes history later but is not implemented.
- The PR changes loop documents and one merge intent only; no runtime, schema,
  migration, tests, workflows, CI, or other initiative files.

## Product behavior and acceptance proof

No product behavior changes. The plan guarantees traversable Submission and
Review predecessor chains, append-only findings/resolutions, one reviewer
contribution per committed Review, and FinalAcceptance plus exactly one
submitter accepted-submission contribution only on `accept`.

## Tests, test delta, and CI integrity

Merge-intent validation, Markdown links, stale wording, `git diff --check`, and
all 89 focused agent gates pass. No test or CI file changed or weakened. Full
backend coverage remains a GitHub Actions requirement for future runtime work.

## Reviewer results and external review

Reviewed code SHA: d4b75e24a62eabdfdba43e0561fedfe32faf6046

Reviewed at: 2026-07-22T03:55:22Z

Reviewer run IDs: /root/plan_arch_review@d4b75e24; /root/qa_product_review@d4b75e24; /root/security_docs_ci_review@d4b75e24

Open sub-agent sessions: none

Valid findings addressed: yes

| Reviewer | Result | Blocking findings | Notes |
|---|---:|---|---|
| senior engineering | PASS AFTER FIXES | None | Boundary and sequence are maintainable. |
| QA/test | PASS AFTER FIXES | None | Lifecycle and cardinality are correct. |
| security/auth | PASS AFTER FIXES | None | Owner/start gates fail closed. |
| product/ops | PASS AFTER FIXES | None | Review/revision operations are traceable. |
| architecture | PASS AFTER FIXES | None | Upstream ownership remains external. |
| CI integrity | PASS | None | No CI control changed. |
| docs | PASS AFTER FIXES | None | Current and archival facts are distinct. |
| reuse/dedup | PASS | None | No duplicate abstraction. |
| test delta | PASS | None | No test changed or weakened. |

These results bind candidate `d4b75e24` against trusted main `14fa4316`.
Fresh GitHub and CodeRabbit review remains required after push.

## Remaining risks and follow-up

Signed loop memory still names retired 02A1 until PLAN3 merges. After merge,
03P requires a separate signed start on exact current main. Every later owner
handoff must be proven by merged chunk/PR/SHA, typed contract, and tests.

## Human review focus and merge ownership

Confirm the `allow_review` boundary, retirement of crossed-boundary work,
lineage and contribution cardinality, and PLAN3 -> 03P -> 03A sequencing. Only
the user may approve and merge this specific PR; merge does not start 03P.
