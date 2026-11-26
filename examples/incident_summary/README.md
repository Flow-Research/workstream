# Incident summary lifecycle pilot

This small real terminal task proves the Workstream path from intake through a verified Submission, post submission work evaluation, revision, and governed acceptance. It checks one fixed, visible input and one computed output. It does not replace the broader Terminal Systems benchmark judge or claim general evaluation capability.

Build the same standalone image for PRE and POST registration with `Dockerfile`. Attach `incident_summary_layout` at PRE and `incident_summary_counts` at POST, each using configuration `{"check":"..."}` for its own check. The image uses the external checker request/result protocol and reads material at `/work/input`. PRE checks root file presence and shape; POST independently verifies the fixed event input and exact counts. Neither phase executes submitted code or calls a model.

`fixtures/correct/summary.json` and `fixtures/incorrect/summary.json` are authentic expected and wrong contributor outputs. Use `package.py` to produce deterministic ZIPs with the same event input. `pre-missing` intentionally omits the summary.
