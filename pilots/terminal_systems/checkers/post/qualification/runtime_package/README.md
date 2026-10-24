# Runtime integration qualification package

This is a deliberately small, runnable package for qualifying the project POST
image and generic trial runtime. It follows the Terminal Systems package
contract, but it is not a delivered project task, an eligibility example, or
evidence for setup/activation. Its only behavior is a deterministic file-state
oracle with explicit initial, reference, incomplete, missing, fabricated,
interrupted, and restarted states.

The package is kept out of the checker image by that image's `.dockerignore`.
The qualification harness stages it as submitted material and retains the real
runner observations before the controlled assessment.
