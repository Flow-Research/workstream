# WS-AUTH-001-12 External Review Response

External review: CodeRabbit run `744220a1-954a-4884-9613-3479b2e68e49`

Reviewed integration head: `480abc17da96272070314a5f90c0a460cfe940ec`

Reviewed repair commit: `697465ec`

Focused repair reviewers: security/auth PASS, docs PASS, CI integrity PASS

## Comments addressed

- Replaced ambiguous prerequisite grammar with explicit “must be merged”
  wording in 12A and 12B2.
- Required 12B2 to activate and verify `project.setup_run.update` membership
  before changing either Celery entry point.
- Added the repository-wide 78 percent coverage baseline beside every flagged
  90 percent child-module obligation.
- Clarified the sufficiency-run boundary: a covered Project Manager requests
  the run over HTTP, while the fixed setup service uses only internal command
  resolution and cannot invoke the public route. Removing human request
  authority was rejected because it conflicts with the parent action matrix.
- Added the owning CON clean cut explicitly to both AUTH-12H sequence records.
- Added the exact reviewed planning HEAD and base SHA to internal evidence.
- Reconciled migration wording after pulling trusted main: ART-owned `0040` is
  merged, AUTH does not reuse it, and 12A still requires planning merge plus a
  separate user start.

## Comments deferred

None.

## Human decisions needed

None. The dual human-request/internal-service-execution boundary was already
fixed by the reviewed parent inventory and is now stated consistently.

## Commands rerun

- `git diff --check`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_workstream_wording.py`
- Hosted `Backend / test` and `Agent Gates` passed on reviewed integration head
  `480abc17`; both must rerun on the pushed repair head.

## Remaining risks

Runtime proof remains owned by each separately started implementation child.
AUTH-12H remains gated on the CON clean cut.
