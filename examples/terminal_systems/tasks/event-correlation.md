# Author a deterministic event-correlation task

## Situation

A support tool combines locally exported event streams into operation summaries.
Repeated delivery, shuffled records and equal timestamps expose defects that do
not appear in a neatly ordered sample. Create a task where the solver repairs the
correlation logic and its observable outputs.

## What you create

Supply a small command-line program, original event fixtures and a documented
input/output format. Use realistic but fictional operation identifiers. Include
a visible example that explains the output without revealing every verification
case. The task must run locally without a logging provider or external account.

## Behavior the finished task must specify

- Event identity determines whether a record is an exact duplicate. Define what
  happens when the same identity appears with conflicting content.
- Timestamp parsing, timezone normalization and tie-breaking are explicit.
  Equal timestamps must actually occur in the supplied verification cases.
- The output contains the required per-operation state and values. Define how
  missing events, unknown event types and malformed records are handled.
- Reordering input records within the documented equivalence rules does not
  change the meaning of the output. Define any output ordering requirement.
- One operation's invalid event cannot silently change another operation's
  summary. State whether the tool rejects a whole input or reports partial
  results, including the corresponding exit status.

Choose a bounded event model and specify it completely. Do not assume that start
and finish events always arrive in timestamp order. Explain exactly how durations
or other computed values are derived, including invalid or incomplete pairs.

## Evidence the task must support

Use duplicate records, conflicting duplicates, timezone-equivalent timestamps,
ties, missing records and shuffled input. Compare parsed output fields with
independently worked expected values. Test the documented error policy and exit
status; counting output rows alone is not sufficient.

Provide a plausible repair that sorts only by timestamp or discards every repeated
identity without checking its content. Show the input where this repair produces
a convincing but incorrect summary.

## Submission

Deliver the full package required by the project guide. The goal is a clear,
reproducible solver challenge, not a fixed-output exercise that can pass by
memorizing the visible sample.
