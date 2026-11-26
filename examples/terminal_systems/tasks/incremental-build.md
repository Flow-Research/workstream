# Author a dependency-aware incremental build task

## Situation

A team uses a small local build planner to regenerate artifacts after inputs
change. It works for a simple chain but mishandles shared prerequisites and can
record a failed build as current. Create a task where the solver repairs the
planner and proves that its produced artifacts remain trustworthy.

## What you create

Provide source for the planner, a compact graph format and deterministic local
build steps. The example graph should include a branching dependency and a shared
prerequisite. Build steps may transform small text or structured files; a large
compiler toolchain is unnecessary. Document the interface for planning, building
and inspecting retained build state.

## Behavior the finished task must specify

- Dependencies complete before their consumers. Define the deterministic order
  for independent ready nodes if order is exposed in an output contract.
- Unchanged inputs reuse valid prior output. A change to an input or a declared
  build recipe invalidates the affected node and its dependents.
- Shared prerequisites are handled once per invocation, and missing output is
  never treated as a valid cache hit.
- A failed step prevents its consumers from being published as successful. A
  later invocation can recover without accepting an incomplete artifact.
- Unknown dependencies and cycles produce a useful failure with no falsely
  completed output.

Specify how changes are identified, how input deletion is handled, and what
happens to previously valid output when a rebuild fails. The task is local; do
not require a remote cache. Parallel execution is optional and must not be an
unstated requirement.

## Evidence the task must support

Build twice with unchanged inputs, then change one branch and inspect exactly
which steps rerun and which artifact bytes change. Include a recipe change,
missing output, failed shared prerequisite, cycle and recovery after failure.
Derive expected affected nodes independently of the planner's own traversal.

Supply an incomplete repair that invalidates only direct dependents or marks a
step complete before its command succeeds. Show why a simple chain test would
miss the error and why your branching or failure case detects it.

## Submission

Deliver the full authoring package with a reference repair, verification and
resource observations. The resulting solver task must assess build correctness,
not familiarity with a particular commercial build service.
