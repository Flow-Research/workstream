# WS-ENG-009 Decisions

## D1 — Atomic active-method cutover

Workstream will not operate `.agent-loop` and Commitrail as simultaneous active
methods. The implementation PR establishes Commitrail and removes the old
method together.

## D2 — Git history is the archive

Historical review bundles, merge intents, queues, recovery records, and closed
planning detail will not be copied into a new in-tree archive. Still-normative
facts are relocated; everything else remains recoverable from Git.

## D3 — One-record default

A meaningful single-PR change uses one combined change record. Additional
records must be justified by multi-PR coordination or material risk.

## D4 — No process authority

Commitrail records explain and evidence work. GitHub permissions, branch
protection, required checks, eligible human approval, and human merge decisions
remain authoritative.

## D5 — Workstream is the first blind evaluation

The first post-cutover bounded Workstream change will evaluate the method using
the documented entry path without legacy compatibility or private procedure.
