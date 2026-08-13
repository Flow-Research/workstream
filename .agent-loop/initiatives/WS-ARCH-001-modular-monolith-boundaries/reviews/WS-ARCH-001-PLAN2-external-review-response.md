# WS-ARCH-001 PLAN2 External Review Response

Comments addressed: all eight actionable CodeRabbit findings were validated
and corrected: CHECKER ownership separation, ART terminology, denial-audit
facts, reviewer-session evidence, planning/implementation ownership wording,
retired coverage commands, the sole post-submit sequence, and roadmap
checker/REV milestone separation. The additional route-removal wording finding
was also corrected.

Comments deferred: none.

Human decisions needed: none.

CI issue addressed: Agent Gates rejected future planning skeletons without
atomic planned-state declarations. Every changed contract now declares
`planned`, and its initiative chunk map, status, and current-state projection
agree. The validator was not weakened.

Commands rerun:

- `python3 scripts/check_chunk_state_sync.py --base-ref 1739a1476f4f3b76ce18d4446cc04a741889cc74`
- `python3 scripts/check_markdown_links.py`
- `python3 scripts/check_stale_workstream_wording.py`
- `python3 scripts/check_stale_authorization_docs.py`
- `python3 scripts/check_stale_artifact_contracts.py`
- `python3 -m pytest -q scripts/test_lightweight_agent_gates.py`
- `git diff --check`

Remaining risks: CodeRabbit and hosted CI must complete against the new exact
head before merge readiness is reported.

## Human L1 plan review amendment

The human review correctly rejected downstream-only CON wording. The plan now
uses `ContributionPolicy`/`ContributionPolicyVersion` as the sole governing
policy model, freezes the submitter version atomically on TaskAssignment,
carries it through canonical `allow_review`, freezes the reviewer version
independently on ReviewLease, and requires ContributionRecord,
CompensationAward, and the CON flush-only participant before the first live
Review decision. Independent REV schema and packet foundations remain free to
proceed behind their own gates.
