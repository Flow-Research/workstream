# Author a restart-safe file-processing queue

## Situation

A small operations team processes locally submitted jobs into result files. A
worker can stop after producing a result but before recording completion. On
restart, the current implementation either repeats the effect or loses the job.
Create a terminal task in which a solver diagnoses and repairs this behavior.

## What you create

Provide a small application, starting source, sample jobs and a documented local
command interface for accepting jobs, processing them, inspecting status and
recovering interrupted work. Choose a suitable language and local persistence
mechanism. Use original data and make the failure reproducible without a network
service or credentials.

The solver must receive a functioning but incorrect application. Do not make the
exercise consist only of filling an empty function or installing a missing tool.

## Behavior the finished task must specify

- Each accepted job has an identifier and immutable input. Repeating the same
  request returns the retained facts. Reusing that identifier for different input
  fails without replacing the original job.
- A completed job has one observable result. Recovery cannot silently duplicate
  its effect or discard a result that was already committed.
- An interrupted job can resume according to a documented recovery rule. Status
  distinguishes unfinished work from a completed result.
- Invalid work does not damage unrelated jobs or erase their history.

You decide the exact formats, command names and commit boundary, and explain them
in `instruction.md`. Define what counts as the job's effect. A useful choice is
publication of a result file plus a durable completion record; make the allowed
state at every interruption point explicit. State whether simultaneous workers
are supported rather than leaving the solver to guess.

## Evidence the task must support

Verification should stop execution at a controlled boundary, restart using the
same retained state and inspect both job records and output files. Avoid relying
only on a timing-sensitive sleep. Include a sequence with completed and unfinished
jobs, exact replay, changed-input replay and invalid work.

Supply a plausible wrong repair that marks work complete before publishing its
result, or repeats publication after a restart. Explain the concrete case that
rejects it. Expected effects must follow from the documented commit rule.

## Submission

Deliver the full authoring package in the project guide, including a reference
repair, independent verification and reproduction notes. The work is the complete
task another solver can attempt, not a report describing queue design.
