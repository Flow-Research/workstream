# Runtime integration qualification package

This is a deliberately small, runnable package for qualifying the project POST
image and generic trial runtime. It follows the Terminal Systems package
contract, but it is not a delivered project task, an eligibility example, or
evidence for setup/activation. Its only behavior is a deterministic file-state
oracle with explicit initial, reference, incomplete, missing, fabricated,
interrupted, and restarted states.

Its restart script writes a fixed expected output. It can recover even an
unrepaired starter and therefore proves transport/control plumbing only; it
does not establish that repaired application code recovers real interrupted
work. The runtime plan uses verified reference state before interruption. The
local synthetic fixture test also exercises its literal-output control from
fresh state; the separate model-plan regression tests actual recovery code.

The package is kept out of the checker image by that image's `.dockerignore`.
The qualification harness stages it as submitted material and retains the real
runner observations before the controlled assessment.
