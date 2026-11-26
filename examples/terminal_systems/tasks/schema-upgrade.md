# Author an atomic local database-upgrade task

## Situation

A desktop tool stores records in a local database. Its next release changes a
record representation, but the upgrade utility can update the version marker
before conversion finishes. Create a terminal task where the solver repairs the
upgrade without losing retained data.

## What you create

Provide a small utility, starting database fixtures generated from original
records, and explicit source and destination schemas. Use a local database engine
available in the declared environment. Choose a conversion with meaningful edge
cases, such as preserving exact fixed-point values while separating one field
into several columns. Avoid private or production data.

## Behavior the finished task must specify

- Every supported source version has an explicit conversion rule. Required
  identifiers and relationships are preserved.
- A successful upgrade produces the destination schema and exact converted
  values before marking that version complete.
- A conversion error or an interruption before commit leaves the prior database
  usable under its original schema and version.
- Running the upgrade again on an already upgraded database has a defined safe
  outcome without repeating a data transformation.
- An unsupported version is rejected without changing the database.

Define nullable values, range boundaries, invalid input and any numeric rounding
rule. State whether concurrent callers are supported. If only exclusive access is
supported, document how contention is reported rather than grading an unspecified
race behavior. Identify the transaction boundary in the solver-facing contract.

## Evidence the task must support

Inspect both schema and retained values after success. Exercise an intermediate
conversion failure, a controlled interruption before commit, exact replay and an
unsupported version. Compare the rejected database with its original usable state.
Expected converted values must be derived independently of the upgrade routine.

Include a wrong repair that advances the version marker separately or commits
converted rows in batches. A fixture whose error occurs after some valid rows
must detect partial application. A happy-path-only case is insufficient.

## Submission

Provide the complete task package, including the reference, verification and
reproduction notes. A design document without runnable starting and repaired
states does not fulfill this authoring assignment.
