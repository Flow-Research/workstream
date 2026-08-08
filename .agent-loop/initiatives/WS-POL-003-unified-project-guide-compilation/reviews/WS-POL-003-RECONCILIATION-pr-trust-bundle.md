# WS-POL-003 Planning Reconciliation PR Trust Bundle

## Intent

Make one unified Project Guide compilation the sole future inference path and
reconcile every remaining AUTH, ART, XINT, POL, REV, and CON dependency before
runtime work resumes.

## Design and scope

- One logical/provider attempt returns sufficiency plus artifact, pre-submit,
  and post-submit proposals before approval.
- Product chunks build hidden behavior; AUTH activates the exact reviewed
  boundary; product owners then perform the live cutover; cleanup deletes old
  paths.
- No database transaction or prepared handle spans provider I/O.
- Tasks, admissions, Submissions, checker runs, reviews, revisions, and
  contribution consumption retain exact unified compilation lineage.
- This PR changes planning and review evidence only. It changes no runtime
  code, migration, action availability, permission, CI threshold, or data.

## Review and evidence

Architecture, security, product/operations, QA, senior engineering, and docs
review passed after resolving dependency and stale-authority findings. Details
are in `WS-POL-003-RECONCILIATION-internal-review-evidence.md`.

The following deterministic checks pass:

```text
python3 scripts/check_stale_workstream_wording.py
python3 scripts/check_markdown_links.py
git diff --check
```

## Remaining risk and human focus

The split POL-03A-06B and AUTH activation records are deliberately
non-executable planning skeletons. Before each starts, it must be expanded on
then-current main with exact paths, commands, and named reviewers. Human review
should confirm the dependency order and that no document restores standalone
guide inference, caller-selected checker execution, or cross-boundary product
ownership.

After merge, the first executable candidate is WS-POL-003-01, subject to a
separate explicit start.
