# Terminal Systems incident summary pilot

A service has emitted the seven incident events in `events.jsonl`. Use terminal tools to inspect the file and write `summary.json` at the archive root. Include exactly one row for each service, sorted by service name. Each `total` counts every event for that service, including repeated events. Each `errors` counts events whose `status` is exactly `error`. Keep the supplied event file unchanged.

The submitted ZIP must contain root files `events.jsonl` and `summary.json`. `summary.json` must be a JSON object with one `services` array. Each row has exactly `service` (string), `total` (integer), and `errors` (integer). The service names are `api`, `scheduler`, and `worker`. An incorrect count is accepted as a Submission but fails post submission evaluation and requires revision. Missing or malformed required files fail intake before a Submission is created.
