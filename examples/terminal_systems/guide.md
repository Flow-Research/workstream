# Terminal Systems — contributor guide

## Purpose and your role

Terminal Systems collects practical software tasks that a person or coding agent
can complete using a terminal. A useful task has a believable starting problem,
a reproducible working environment, and a clear way to distinguish a correct
result from an incomplete repair.

Your assignment is to **author a task package**. A later solver will receive its
instructions and starting workspace. You provide that workspace, a reference
repair, and an independent verification suite. Submitting only a solution to the
brief does not complete the authoring assignment.

Work can involve applications, data tools, storage, build systems or operations.
Select the language and tools that fit the problem. The initial assignments do
not restrict the project to those subjects or identifiers.

## Develop the brief into a complete problem

Begin with a situation an engineer could encounter: something observable is
wrong, a capability is missing, or a documented guarantee is not being met. Give
the solver the information and local tools needed to investigate it. Avoid
unrelated puzzles, hidden requirements and arbitrary complexity.

Your `instruction.md` must explain:

- the starting behavior and the result the solver must produce;
- the supported commands, inputs, outputs and observable failure behavior;
- which files may change and which interfaces or existing data must be preserved;
- important boundary rules, such as ordering, retry semantics or numeric precision;
- how to run the application and any solver-visible checks.

Define every rule that affects the result. Small examples can clarify an
interface, but a solver must implement the general behavior rather than return
those examples verbatim. A requirement may permit several valid implementations;
the verifier should accept them all unless the instructions justify a narrower
constraint. Do not grade undocumented wording, internal function names or an
incidental directory order.

The authoring brief deliberately leaves implementation choices to you. Make those
choices explicit in the final solver instructions. If the brief and this guide
conflict, ask for a project clarification before relying on either interpretation.

## Deliver one task package

Submit a ZIP with these paths directly at its root, without an enclosing folder:

| Path | What belongs here |
|---|---|
| `instruction.md` | The complete solver-facing problem. |
| `task.toml` | The metadata and execution contract described below. |
| `environment/` | Dockerfile, dependency locks and build inputs. |
| `workspace/` | The initial source, configuration and data the solver receives. |
| `solution/` | Your reference repair and any supporting source. |
| `tests/` | Verification code, independent expected results and test fixtures. |
| `AUTHOR_NOTES.md` | Design rationale, requirement-to-test coverage and reproduction evidence. |

Additional directories are welcome when they serve the task; explain their role
in `AUTHOR_NOTES.md`. Do not include caches, development history, unrelated output,
credentials, personal records or material you cannot redistribute. Use original
small datasets or appropriately licensed inputs with their notices and origins.
Do not disguise another organization's task or copy a private submission.

Keep author-only material out of the solver's view. The solver receives
`instruction.md`, the starting `workspace/`, and the runnable environment.
Reference code, hidden test data, expected results and author notes must not be
baked into that environment, including earlier container layers. Visible examples
may be included when the instructions identify them as examples.

## Task metadata

Use the following project format for `task.toml`. These are project conventions,
not a required language or application design. The example below illustrates the
shape; replace its sample values with your actual task's values.

| Field | Meaning |
|---|---|
| `format_version` | Integer `1` for this documented project format. |
| `id` | Stable lowercase slug using letters, digits and hyphens; start with a letter, maximum 80 characters. Choose a meaningful identifier rather than copying an example. |
| `title` | Nonempty human-readable task title. |
| `environment.dockerfile` | Relative regular-file path to the Dockerfile. |
| `environment.context` | Relative directory used as its build context. |
| `environment.platform` | Explicit Linux container platform, such as `linux/amd64` or `linux/arm64`. |
| `reference.command` | Nonempty array of command arguments that applies the reference repair. |
| `reference.working_directory` | Relative directory where that command starts. |
| `verification.command` | Nonempty array of command arguments that verifies the resulting workspace. |
| `verification.working_directory` | Relative directory where verification starts. |
| `resources.cpu_millis` | Positive integer CPU allowance; `1000` means one CPU. |
| `resources.memory_bytes` | Positive integer memory allowance. |
| `resources.disk_bytes` | Positive integer scratch-disk allowance. |
| `resources.build_timeout_seconds` | Positive integer limit for building from prepared inputs. |
| `resources.reference_timeout_seconds` | Positive integer limit for one reference run. |
| `resources.verification_timeout_seconds` | Positive integer limit for one verification run. |

```toml
# Shape example only: these paths and allowances are not a runnable task.
# Each author supplies real files, appropriate commands and measured trial notes.
format_version = 1
id = "example-local-tool"
title = "Repair a documented local tool"

[environment]
dockerfile = "environment/Dockerfile"
context = "."
platform = "linux/amd64"

[reference]
command = ["sh", "solution/apply.sh"]
working_directory = "."

[verification]
command = ["sh", "tests/run.sh"]
working_directory = "."

[resources]
cpu_millis = 1000
memory_bytes = 536870912
disk_bytes = 1073741824
build_timeout_seconds = 300
reference_timeout_seconds = 120
verification_timeout_seconds = 120
```

All paths are relative to the task-package root. The working directory may be
`.`. Paths must stay inside the package; absolute paths and `..` segments are not
valid. Commands are argument arrays, not strings with implicit shell expansion.
If a script needs an interpreter, name it in the array and provide it in the
environment. Declare any supplementary metadata in an optional `[extensions]`
table and explain it in the author notes; it cannot introduce unstated grading
rules. The listed fields are required, and other top-level fields are not part
of format version 1.

During author validation, stage a fresh package and give the reference a writable
copy of `workspace/`. Apply the reference there, then verify that resulting
workspace. The verifier must not apply a repair. The same verifier must also run
against a fresh untouched workspace and an intentionally incomplete repair.
Only workspace state may differ between these cases; do not select results based
on whether a reference or solver is running. Keep verifier inputs and expected
results protected from changes made by the solver.

Commands must finish unattended and return zero on success or nonzero on failure.
A verification process must fail when a required assertion fails. State outputs
and diagnostics clearly enough to identify the failed requirement. Resource
allowances describe the whole run, including child processes. Record measured
usage separately from the allowances; do not label an estimate as a measurement.

## Build and execution environment

Make the environment reproducible from declared inputs. Use digest-pinned base
images and exact dependency versions or lockfiles. Include a dependency inventory
in the author notes: source, version or digest, license and purpose. Disclose
which dependencies need to be placed in an offline image store or cache before
building. A digest identifies content; it does not make unavailable content local.

Evaluation must be possible without downloading anything. Prepare build inputs
and runtime dependencies in advance, and document the preparation procedure.
Avoid external accounts, hosted APIs, privileged containers, device access or a
host container socket. Raise an environment requirement that cannot satisfy
these constraints before completing the task.

The solver, reference and verifier run without administrator privileges. Use
writable workspace and temporary directories for their work. Do not rely on a
particular author's home directory, credentials, timezone or machine cache. Do
not assume one platform's timing or filesystem ordering is universal.

Use independent fresh state between trials. Seed randomness when relevant and
make time-dependent inputs explicit. If a numeric tolerance is necessary, state
it in the solver instructions and use the same tolerance in verification.
Performance requirements need a reproducible workload and justified limits;
wall-clock speed on your workstation alone is not a correctness criterion.

## Reference repair and independent verification

The reference must carry out the requested computation or repair from the supplied
starting state. It must not obtain answers from hidden verification fixtures or
simply install precomputed outputs. Explain the important decisions so another
author can investigate a disagreement.

Establish expected outcomes from the written rules independently of the reference.
For small cases, a hand-worked result is useful; for larger cases, explain the
separate method used to establish the expected result. Do not generate the only
expected outputs by calling the code being graded.

Verify the effects that matter. If a task promises retained records, inspect those
records. If it promises recovery, inspect state across an actual interruption and
restart. If it promises a produced artifact, inspect that artifact's contents.
A success message or process exit alone does not establish these guarantees.

Exercise the main behavior, boundary cases and at least one meaningful interaction
between requirements. Include inputs that differ from the visible examples so a
hardcoded answer is inadequate. Check every documented command and failure
behavior that forms part of the task. Prefer behavioral checks over constraints
on a solver's internal implementation.

Before submitting, demonstrate all of the following:

1. The unchanged starter fails a substantive task requirement. An unavailable
   dependency or a broken test command does not count as that failure.
2. The reference passes the full suite in three independently prepared workspaces.
3. At least one plausible incomplete repair fails a named requirement despite
   handling an ordinary case. Supply a reproducible way to apply that repair in
   an author-only location and explain why its rejection matters.
4. Verification rejects missing or fabricated required output and does not alter
   the workspace to make it correct before grading it.

Do not weaken an assertion merely because it disagrees with the reference. Resolve
the discrepancy against the specification. Missing coverage is a limitation to
fix or disclose, not proof of success. Do not claim measured task difficulty
without a real solver evaluation that supports the claim.

## Author notes and revisions

`AUTHOR_NOTES.md` should let another engineer reproduce your observations. Include
an explanation of the defect or missing capability, a mapping from requirements
to verification cases, dependency provenance, exact reproduction commands, trial
outcomes, measured resource use and known limitations. Separate what was executed
from what is only expected. Keep outputs concise and free of credentials or
unrelated machine details.

On feedback, repair the complete package, rerun affected checks and explain the
change. Continue to meet the task's objective; do not narrow it to match a failing
implementation. Your assignment's displayed policy controls revision eligibility
and timing. This guide does not promise additional attempts or override those
terms.
