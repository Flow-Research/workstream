# WS-REV-001-01 Internal Review Evidence

Reviewed code SHA: `e239282e7d2a2b4d46137707f673f76fda55e4b8`

Trusted main SHA: `0ffdabf3dbb77e4e066683fde1a095d744ff1f43`

Reviewed at: `2026-07-18T09:40:12Z`

Reviewer run IDs: `/root/rev01_senior_arch_reuse`, `/root/rev01_qa_product_test`, `/root/rev01_security_docs_ci`

Open sub-agent sessions: none

Valid findings addressed: yes

## Reviewer Results

| Reviewer | Result | Blocking findings | Notes |
|---|---|---|---|
| Senior engineering | PASS | None | AUTH-09B is historical, AUTH-09C is current, and future catalogue counts remain dynamic |
| QA/test | PASS | None | All 80 main tests plus seven REV tests, exact 71-entry scope, and 87 executed gates verified |
| Security/auth | PASS | None | AUTH-09C activates only two bounded reads; all 24 REV dependencies remain unavailable |
| Product/ops | PASS | None | AUTH reconciliation changes no review lifecycle, runtime scope, or Chunk 02 behavior |
| Architecture | PASS | None | REV/AUTH/ART/CON ownership and current-main versus archival-base separation remain correct |
| Docs | PASS | None | AUTH-09C 65/12/53 current state and historical catalogue provenance are consistent |
| Reuse/dedup | PASS | None | Git status output and existing gates are reused without a parallel global scope mechanism |
| Test delta | PASS | None | All 80 trusted-main tests are AST-identical; seven REV tests add coverage |
| CI integrity | PASS | None | Conflict resolution preserves every gate, workflow, threshold, and exact A/M scope check |

## Finding Disposition

Earlier exact-SHA reviews are historical after the CON PR #142 and AUTH-09B
PR #143 main merges and the subsequent repair cycles. Every valid finding was
repaired before this review: FinalAcceptance field/provenance drift, canonical
transaction ordering, planned availability, automated exact CheckerRun
admission, checker versus Review-rooted revision lineage, non-mutating reject
sampling, executable structural regression coverage, and exact AUTH-09B
provisioning/action availability. PR #145's initial CI finding also aligned the
successor heading to the reviewed schema-v2 merge-intent title without starting
Chunk 02. CON-01's active specification and ADR 0016 were then adopted as
canonical CON authority without claiming runtime or removing downstream gates.
Candidate `694c02ac` received a fresh complete review rather than inheriting any
earlier approval. CodeRabbit then reported nine actionable findings and one
Markdown lint nit. The repair made FinalAcceptance an accept side effect,
strengthened exact CheckerRun transition guards, clarified TaskAssignment
attribution, aligned both ART v2 storage passages, generated all `--all`
PlantUML sources before conversion, repaired template tables, required explicit
false revision-limit auto-reject configuration with runtime enforcement deferred
to Chunk 02, and narrowed the scanner to reject truthy forms without rejecting
the required false form. A first repair candidate failed CI integrity only on
Ruff formatting; that mechanical defect was corrected. Candidate `f2493df`
then passed the plan gate and all nine reviewer tracks from fresh exact-SHA
review. ART-02A3 PR #141 later advanced main to `a10d901`, replacing v1 with
the active byte-only v2 LocalStorage clean cut. The branch merged that main,
combined ART's exact byte operations with REV's narrow typed-capability rule,
and retained S3/MinIO, submission/checker cutover, packet-read, and evidence
candidate/finalize as later gates. Candidate `3572835` failed only because four
merged ART assertions were not Ruff-formatted. Candidate `ca6b46b` contains the
mechanical repair and passed the plan gate and all nine reviewer tracks against
the new trusted main. CodeRabbit's next review correctly required the final
PR-scope listing to fail closed. Candidate `7742730` added a path-only
allowlist and documented why trusted current main, rather than the planning
base, defines current PR scope. Internal security/docs/CI review then found the
path-only form could not distinguish an approved modification from deletion of
that same file. Candidate `7785b832` replaces it with an exact
`--name-status --no-renames` A/M manifest. All 71 statuses match, while
adversarial status-change, removal, rename-as-D+A, and addition probes fail.
Candidate `5af0adc` adds only the required accurate review-log entry, and a
final exact-SHA review passed the plan gate and all nine tracks. AUTH-09C
PR #146 later advanced main to `0ffdabf3`. The branch resolved the single shared
agent-gate conflict without removing or semantically changing any of main's 80
tests and retained all seven REV additions. Candidate `f1004158` passed eight
tracks, but plan/senior review found three records that still called AUTH-09B's
65/10/55 snapshot current. Candidate `a184e411` labels AUTH-09B historical,
AUTH-09C 65/12/53 current, and later release totals dynamic. Fresh exact-SHA
review passed the plan gate and all nine tracks. CodeRabbit then found that the
committed-range manifest could not detect a dirty worktree. Candidate
`e239282e` adds the required clean porcelain-v1 precondition. Isolated staged,
unstaged, and untracked probes fail as required, and all nine exact-SHA tracks
pass.

## Deterministic Evidence

- `python3 scripts/test_agent_gates.py`: 87 passed.
- All stale artifact, authorization, review-contract, and Workstream wording
  scanners passed.
- Markdown link validation passed for 56 changed Markdown files.
- Ruff format and lint passed for both changed Python gate files.
- All reference-spec checksums passed; the WS-REV and WS-IMP archival pairs are
  byte-identical to trusted base.
- PlantUML 1.2026.6 matched SHA-256
  `89948f14c93756c7a3fb7b69078ff37e8489fd79dd430c582b931e2f65358690`.
  Pinned `--review-context` and isolated `--all` renders succeeded. The `--all`
  run proved all four SVG sources render before conversion; out-of-scope future
  diagram output was not committed. Prior repeated review-context renders
  remained byte-identical, and visual inspection found no clipping or overlap.
- The two unrelated context images remain byte-identical to trusted base.
- Both local roadmap exports remain absent and no `sheets/` file is tracked.
- Exactly one merge-intent file exists for this chunk and `git diff --check`
  passed.
- The committed 71-entry reviewed-scope manifest exactly matches
  `git diff --name-status --no-renames 0ffdabf3dbb77e4e066683fde1a095d744ff1f43...e239282e7d2a2b4d46137707f673f76fda55e4b8`.
  The clean-worktree prerequisite passes; simulated staged, unstaged, untracked,
  status-change, removal, rename, and addition states fail the proof.

## Residual Risks

Runtime concurrency, database constraints, rollback behavior, and live
AUTH/ART/CON integration remain obligations of later implementation chunks.
The regex scanner is intentionally conservative and may need new fixtures for
future valid or prohibited phrasing. Rendering is pinned and repeat-checked,
but still relies on the documented host Pandoc, WeasyPrint, ImageMagick, JRE,
and font environment.
