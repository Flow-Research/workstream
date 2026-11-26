# Author a verified directory-restore task

## Situation

A local backup utility can list a snapshot, but its restore path modifies the
current destination before it knows whether the snapshot is valid. A damaged
snapshot can leave a mixture of old and restored files. Turn this into a practical
repair task with an explicit publication boundary.

## What you create

Supply a small implementation, an original fixture directory and documented
snapshot/restore commands. Include nested directories, an empty file, a filename
with spaces and two files with the same length but different contents. The solver
should be able to demonstrate the failure using the supplied tools.

Keep the format small enough to inspect. Choose a local manifest and content
layout rather than relying on an external backup service. The task need not be a
general-purpose backup product.

## Behavior the finished task must specify

- A manifest identifies the required paths, entry types, content lengths and
  content digests. Restore checks the complete declared content.
- Invalid content, a missing object, duplicate destination paths or a path outside
  the restore root cannot produce a successful restore.
- Until publication succeeds, a failed attempt leaves the prior destination's
  content intact. Define exactly what may remain in temporary storage and how a
  later attempt handles it.
- Successful restore produces the specified tree, including empty directories
  and files. State how extra files in an existing destination are treated.
- Repeating a successful restore has a documented result and does not corrupt
  the retained snapshot.

Define which metadata is preserved; do not leave permissions, timestamps or links
implicitly graded. You may exclude unsupported entry types if the instructions
state that they are rejected. Choose and explain the publication mechanism and
supported filesystem assumptions.

## Evidence the task must support

Compare destination contents before and after rejected restores. Exercise a
corrupted object of unchanged length, a missing object and an interruption before
publication, then repeat recovery. Inspect the final tree rather than accepting a
success message. Use independent content digests and known original fixture bytes.

Include a plausible incorrect repair that validates only lengths or validates
files after overwriting the destination. Show the specific assertion that exposes
it while an ordinary restore still succeeds.

## Submission

Provide the complete package required by the project guide. Your reference and
verification must demonstrate the declared filesystem guarantees, not guarantees
that depend on an unstated platform feature.
