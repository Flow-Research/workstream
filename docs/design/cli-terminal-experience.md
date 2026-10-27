# Workstream contributor terminal workbench

This is the presentation contract for the opt-in `workstream tui` contributor
workbench after [WS-CLI-001-51](../../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-51.md),
extending the presentation established by [WS-CLI-001-50](../../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-50.md).
It describes the intended merged interface, not a new API, deployed service,
published binary, or completed product journey. The existing read and download
boundaries are recorded in [WS-CLI-001-48](../../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-48.md)
and [WS-CLI-001-49](../../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-49.md).
Explicit commands in the [CLI reference](../../cli/README.md) remain the
non-interactive interface for humans and agents, with their existing text, JSON,
arguments and exit behavior.

## Scope and truth boundary

One launch opens an exact-grant project picker, not a system project catalogue.
Within the selected project, visible collections are `Ready`, active `Mine`,
and owned `Submissions`. Ready offers fresh contributor-safe task detail. Active
Mine offers `Overview`, `Context`, `Intake`, and `Guide`; an owned Submission
offers `Overview` and paged `Findings`. Contribution Evidence is an inert CLI
handoff, not a fourth fetched collection. The project picker uses `me projects`;
the separate system-reader `project list` does not feed this workbench.

The workbench exposes deliberate exact-task Claim and Start. It exposes no
preparation, Submission, Review, policy, management or payment mutation. Its only
local file write is an explicitly confirmed, verified single-guide-document
download. It does not poll, automatically retry, cache stale authority, store
credentials or history, acquire tokens, launch a shell or viewer, or copy a
command to the clipboard. It uses the existing typed public client and the
supplied `WORKSTREAM_API_URL` and `WORKSTREAM_TOKEN`; there is no Workstream
login. A profile read may have the backend's existing actor admission,
last-seen and audit effects; reads are not unaudited server interactions.

## Claim, start and uncertain outcomes

`a actions` is available on an exact freshly inspected Ready task with `ready`
status, or Mine Overview with `claimed` task status. Assignment status on a Mine
row is not task status and cannot select Start. Each action requires a caller-
supplied UUID and confirmation of the exact actor/project/task/action/key and
available locked terms. Explain and acknowledge saving the action, task and key
outside this session before dispatch; the application cannot verify that external
save. It generates no fallback key and stores no operation history. Reason is
omitted consistently through the existing typed client.

Enter advances from key entry to confirmation; `s` acknowledges the external-save
warning. Confirmation is not dispatch until explicit `y` at a usable size. `p`
opens explicit same-packet replay, with the same acknowledgment and confirmation.
Text entry,
confirmation and pending-write states consume their own keys; navigation,
refresh and repeated keys cannot duplicate or replace a pending POST. Claim
never automatically starts work. Backend authorization remains fresh on every
call, including exact replay. Validate selected-project and claim actor binding
in addition to the typed client's task/receipt checks.

Unknown outcome retains the exact packet and requires explicit unchanged replay.
Transport loss, cancellation or a malformed success is not rejection or rollback.
A canonical denied replay does not erase earlier uncertainty. A confirmed receipt
is independent of a subsequent read failure; no failed refresh undoes a confirmed
write. Clear protected descriptions and terms on denial and disable in-session
replay after session failure. Retained recovery references are minimal and inert.
Quit cancels the request, not server effects. On restart the caller must use their
saved action/task/key with the explicit CLI, same API origin and actor; there is
no automatic crash-recovery claim. Claim replay after advancing to start may
validly conflict because backend replay is state-dependent.

Every displayed fact belongs to its returned scope. List rows are observations,
not reservations, current eligibility, or authority for a later command.
Checker runs and findings are evidence, not acceptance decisions. Only a stored
Submission outcome can say `evaluation_pending`, `review_pending`, `needs_revision`, `rejected` or
`accepted`; the TUI does not infer one from passing checks. Contribution records
are earned facts, not payment or fulfillment proof. The default locked
ReviewPolicy requires human review; supported false-policy acceptance is an
authorized backend operation, never a checker-owned or fabricated Review.

## Reading and navigation

The header identifies `WORKSTREAM / Contribute` and the selected project name.
The active collection and, where applicable, active detail section remain
visible with textual selection markers. At 120×40 the worklist occupies a
stable left pane (about 36 cells) and the main reading area occupies the right.
Only the right detail pane scrolls while reading task or Submission detail;
the left worklist retains its selected row. A guide confirmation replaces the
normal panes with a scrollable exact-target review. At widths of at least
100 cells and heights of at least 24 rows, use two panes. Smaller usable
terminals use sequential, single-column list and detail views; `--plain`
always uses that layout, even on a wide terminal. Reflow preserves selection,
exact project, section and confirmation target, and dispatches no request.
At less than 40×10, show only resize and context-appropriate quit guidance.
`q` exits outside text entry; Ctrl+C always exits. Hidden content
cannot be selected and `y` cannot stage or dispatch a download. Restoring size
still requires deliberate confirmation.

Excerpted 120×40 fixture render; ellipses below omit rows, not UI content.
This is terminal rendering evidence, not a live-backend claim:

```text
WORKSTREAM / Contribute / Aster Research / fixture project
Ready  [Mine]  Submissions
[Overview]  Context  Intake  Guide
...
> Assess the coastal... [active]     | Assess the coastal flood warning study and document where its evidence supports
                                     | the published conclusions
                                     | Stored status: in_progress
                                     | Skills: evidence synthesis, research
...
                                     | Instructions
                                     | Read the supplied field report and produce an evidence matrix linking each major
                                     | conclusion to its source. Keep direct observations separate from assumptions.
...
                                     | Acceptance criteria
                                     | Every conclusion has a traceable citation or an explicit evidence gap. The matrix
...
                                     | Rejection criteria
...
                                     | Contribution terms
                                     | Accepted submission terms: money / USD / 40.000000000000000001
                                     | Completed review terms: unpaid
                                     | Terms are potential earned terms, not acceptance or fulfillment.
...
                                     | References
                                     | Task: 30000000-0000-7000-8000-000000000001
...
page 1 | loaded 1 | observed 18:09:50
arrows scroll  Tab section  Esc back  r refresh  g projects  c CLI  ? help  q quit
```

The drawing demonstrates hierarchy only: a row preview cannot contain full
instructions, criteria, locks, or terms before an exact detail read. In task
detail, show the full instructions and acceptance criteria before locked terms
and references, using wrapped paragraphs and readable spacing. Terms stay
potential and separate for an accepted Submission and completed Review, with
exact instrument, unit and decimal-string quantities from the locked version.
Retain exact task, assignment, Submission, policy and guide IDs, digests/hashes,
and decimal strings in their relevant detail sections; presentation must not
round, silently truncate, or replace them with a color or badge. Ready details
show only the fields actually returned for that scope. Mine Overview leads with
the work to do; Context, Intake and Guide expose their existing distinct reads.
Submission Overview presents the stored outcome/reason separately from Findings.

Before inspection, the preview shows only facts already in the loaded row,
with an `Enter to inspect` cue. Moving a row or changing the preview makes no
request. `Enter` requests fresh exact-resource detail; opening Context, Intake,
Guide or Findings uses its existing scoped read. `n` requests one continuation
page, never walks pages in the background. `/` filters only loaded row titles
or names and says so; it is not search across pages. Refresh resets the current
page's cursor. The collection/section header identifies the resource; the fixed status line shows loaded row/run
count, current page, whether a continuation was returned, and local observation
time. It never presents loaded-page length as a total, a server timestamp, or
an inferred project-wide count. Loading is explicit. A failed read clears the
affected current content and continuation and reports unavailable or denied,
with safe server code/correlation ID when present; it never leaves old protected
content on screen with a merely cosmetic stale label. Session loss clears work
data and requires relaunch with a valid environment token. Late canceled reads
cannot restore a previous actor, project or resource.

### Guide and Findings

Guide lists the locked document metadata supplied to the active Mine context.
Metadata, including a returned hash, is **not** a verified-byte claim. `d`
opens destination entry for the selected document; the directory must already
exist. `Enter` advances to a scrollable confirmation that names the exact
document label and ID, task ID, destination path, UUID filename, expected byte
count and hash. It starts at the target heading. Only `y` with that confirmation
visible initiates the existing verified download. `Esc` cancels. The shared
download owner uses private staging, checks the bytes, then publishes one final
file without replacing an existing path; cancellation or failure cleans up and
does not report a verified save. No PDF/Office renderer or automatic open runs.

Findings loads a single page for the selected owned Submission and retains each
run's exact ID and current flag. Display returned check ID, status, severity,
message, suggested fix and optional path/line without inventing missing
fields. Separate blocking, warning and `coverage_incomplete` evidence from the
stored Submission outcome. `n` fetches only the returned findings continuation;
`r` refreshes that read. Neither a pass nor a coverage gap is a TUI decision.

### Keys and handoff

`?` groups help by Navigate (arrows, `Tab`, `Esc`), Inspect (`Enter`, `r`, `g`,
`/`), Pages (`n`), Guide downloads (`d`, destination `Enter`, confirmation
`y`/`Esc`), and Exit (`c`, `q`, Ctrl+C). There are no independent pane-focus
keys. `1`, `2`, `3` directly select Ready, Mine and Submissions from ordinary
views; Shift+Tab reverses collection/section navigation. Show only applicable
keys in the contextual footer. `q` is ordinary text inside filter, replay-key or directory
entry; Ctrl+C always exits. Help and inert handoff may scroll without changing
selection or sending a request. `c` shows the equivalent existing CLI command
as separate, inert argv arguments, never an executable shell string, and never
includes a bearer. Where no exact command recipe is available, say so.

## Color, text and terminal support

Use a quiet slate canvas, cyan focus and peach deliberate-action accent, with
readable light-background and ANSI-16 equivalents. Selection, severity and
action meaning also have words and markers. The terminal's background response
selects the palette; without that response, keep neutral terminal-default text
rather than assume a dark background. The bare Windows ConPTY test host exercises
this neutral fallback; it does not prove colored-host response transport. Native
POSIX tests exercise detected palettes, and model tests exercise exact palette
rendering on all supported operating systems. `NO_COLOR` disables application
color; `--plain` uses ASCII, no application colors or alternate screen, and
single-column layout. It still needs interactive cursor controls. The TUI
rejects non-TTY/JSON launch before an API request and points automation to
the explicit CLI. Wrapping and width calculations are in terminal cells,
including Unicode. At 40×10 and above, no essential label is available only
as clipped text. Untrusted response text cannot emit ANSI/OSC, controls or
bearers; prose may retain safe line breaks while IDs and labels stay strictly
escaped. Color does not signal authority, completion, or a synthetic progress
percentage.

## Future boundary, not current behavior

The broader [WS-CLI-001 initiative](../../.commitrail/initiatives/WS-CLI-001/OVERVIEW.md)
retains separate in-TUI Contribution Evidence, preparation/submission and management
boundaries. Evidence first needs a shared typed single-page contribution port;
the complete explicit CLI export is not a TUI page source. Human Review and
fulfillment are separate product gaps, not empty workbench screens. A later
system-reader picker may consume the distinct authorized project catalogue;
it must not turn exact-grant contributor membership into system discovery.

Before generated-key or automatic restart recovery ships, its specific public
operation needs durable private custody of exact unchanged inputs before one
request, including actor/API origin and any
caller-owned key, admission, lineage acknowledgement or source-file digest.
An unknown response requires operation-specific recovery, never automatic
retry or inference from an empty history page. Claim/start keys, preparation's
ZIP/packet/key, Submission's admission/packet, guide correction receipts, and
Operator retry/reconciliation selectors are not interchangeable. Design and
prove each flow at its own boundary; do not add a generic write journal or
silent handoff. Claim/start currently use externally saved caller-owned keys,
matching the explicit CLI, not automatic custody. The historical design decisions
and separate operation records remain in the [initiative overview](../../.commitrail/initiatives/WS-CLI-001/OVERVIEW.md).
