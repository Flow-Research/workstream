# Observability Operations

Workstream has implemented one privacy-bounded diagnostics path for the API and
prefork Celery processes. The implementation creates structured logs, explicit
HTTP and task spans, and closed application metrics. It does not mean that an
OTLP collector, dashboard, alert, or monitoring service is configured or
deployed. Durable audit records remain the authority for product decisions;
diagnostic identifiers and trace context never authorize an operation.

## Configuration

The API and Celery process should receive the same bounded settings. They use
the fixed service names `workstream-api` and `workstream-celery`.

| Setting | Default | Contract |
|---|---:|---|
| `WORKSTREAM_OBSERVABILITY_LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT` | unset | Optional credential-free collector origin. Local and test environments may use HTTP; staging, preview, prod, and production require HTTPS. |
| `WORKSTREAM_OBSERVABILITY_TRACE_SAMPLE_RATIO` | `0.1` | Local root sampling ratio from `0.0` through `1.0` |
| `WORKSTREAM_OBSERVABILITY_EXPORT_TIMEOUT_SECONDS` | `2.0` | Per-export bound from `0.1` through `10.0` seconds |
| `WORKSTREAM_OBSERVABILITY_SHUTDOWN_TIMEOUT_SECONDS` | `3.0` | Whole runtime shutdown wait from `0.1` through `10.0` seconds |

Export is opt-in. With no endpoint, Workstream still emits safe JSON logs and
runs the explicit instrumentation without an external trace or metric reader.
An invalid endpoint fails startup with a fixed error that does not echo its
input. The endpoint rejects credentials, paths, query strings, and fragments.
If a collector requires authentication, supply standard OTLP headers through
the deployment's secret environment, such as `OTEL_EXPORTER_OTLP_HEADERS`;
never put them in the endpoint or committed environment files.

The runtime joins `v1/traces` and `v1/metrics` to the configured collector
origin and uses OTLP over HTTP/protobuf. Export queues, batches, request
timeouts, force-flush, and
shutdown waits are bounded. Missing configuration disables export. Once valid
configuration has passed startup validation, exporter construction failure,
collector refusal or timeout, and flush or shutdown failure do not change API
responses or task outcomes. A failed exporter produces only a constant safe log
event. Operators must monitor collector health separately because Workstream
deliberately keeps product flow fail-open to diagnostic outages.

## Privacy and cardinality

JSON logs use a closed field set: timestamp, fixed service and environment,
severity, fixed event, and validated request, correlation, trace, and span IDs
when present. The formatter never renders a dynamic log message, interpolation
argument, exception, traceback, or arbitrary extra. Workstream takes over the
configured Uvicorn access/error and Celery/Kombu logger handlers so their
default messages cannot disclose paths, query strings, task arguments, retry
reasons, broker URLs, or exception content.

The explicit HTTP path records a registered route template, normalized method,
status class, fixed outcome, and validated diagnostic IDs. The task path records
only a registered task name, fixed outcome, and validated diagnostic IDs. It
records no headers, body, raw URL or query, guide/task/prompt/ZIP content,
signed URL, credential, SQL text or parameter, exception message, stack, or
span event. Metric attributes exclude every record, actor, user, project,
request, correlation, trace, and span ID. Unknown routes, methods, tasks, and
outcomes collapse to fixed `unmatched` or `other` values.

Public HTTP always starts a fresh random local trace. Incoming `traceparent`,
`tracestate`, baggage, caller trace IDs, and caller sampled flags cannot choose
the local trace or sampling result. Trusted internal broker publication strips
those inputs and propagates only the locally created `traceparent` plus the two
canonical Workstream diagnostic UUID headers. The Celery child initializes providers
after prefork and resets every context token on normal, failure, and retry exits.
OpenAI Agents SDK tracing and sensitive trace inclusion remain disabled.

## Signal inventory

The API emits one `SERVER` span named `HTTP {method} {route}` for every HTTP
request. Its attributes are `http.request.method`, `http.route`,
`http.response.status_class`, `workstream.outcome`, and the validated
`workstream.request_id` and `workstream.correlation_id` when present. The
Celery process emits one `CONSUMER` span named `celery {task}` with
`messaging.destination.name`, `workstream.outcome`, and the same optional
diagnostic IDs. Neither span form exports events, links, status descriptions,
or arbitrary instrumentation metadata.

| Metric | Unit | Attributes | Meaning |
| --- | --- | --- | --- |
| `workstream.http.server.duration` | `s` | method, registered route, status class, outcome | Time spent serving one HTTP request |
| `workstream.http.server.active_requests` | `{request}` | method | Balanced increment/decrement for requests currently executing |
| `workstream.celery.task.duration` | `s` | registered task, outcome | Time spent executing one Celery task attempt |

Methods, routes, task names, status classes, and outcomes pass through fixed
inventories. Unknown values become `other` or `unmatched`; identifiers never
become metric attributes.

## Trace boundaries

Direct API-to-Celery publication keeps a parent-child trace while both
processes are running. The durable outbox does not persist trace context in a
business row, payload, digest, schema, or authorization input. Therefore,
outbox recovery after a process boundary honestly begins a new trace. Once the
canonical invocation envelope is committed, the active Celery span may include
the envelope's existing correlation ID for investigation. That value remains a
diagnostic annotation, never a metric label or authority fact.

## Operational drill

Use a local Redis instance and the repository's isolated PostgreSQL runner for
the four practical checks below. Never place a real token, credential, query,
payload, prompt, archive, or signed URL in a canary.

1. Run the configured-logger privacy proof and inspect its JSON output. Every
   record must contain the expected fixed service role and no canary text.
2. Run the real-prefork correlation proof. Confirm the API server span and
   Celery consumer span share the expected parent-child trace, the child PID
   differs from the parent, and the next task with missing or malformed headers
   inherits no diagnostic context.
3. Run the collector-failure proof with no endpoint, exporter-construction
   failure, and a refusing or timing-out local endpoint. API responses and
   Celery task outcomes must remain unchanged, while only the constant
   `observability_export_unavailable` event is logged.
4. Run
   `tests/outbox/test_delivery_postgresql.py::test_diagnostic_annotation_follows_committed_invocation_envelope`
   through `scripts.run_isolated_tests`. Compare the before/after snapshots:
   no business row, payload, digest, authorization input, or schema changes.
   Recovery starts a new trace, while the committed outbox correlation ID may
   annotate only the current span.

The focused privacy, outage, and correlation commands are:

```bash
cd backend
WORKSTREAM_TEST_BROKER_URL=redis://127.0.0.1:6379/15 uv run pytest -q \
  tests/test_observability.py::test_real_loggers_and_hostile_exception_never_render_sensitive_values \
  tests/test_observability.py::test_collector_failure_is_bounded_and_product_flow_succeeds \
  tests/test_celery_observability.py::test_real_celery_prefork_correlates_api_and_resets_sequential_task_context
```

## Troubleshooting and profiling

Start with the constant `observability_export_unavailable` event and collector
health. Verify network reachability from both API and Celery processes, the
credential-free endpoint origin, secret-injected OTLP headers, and collector
support for OTLP HTTP/protobuf. Do not enable framework, Celery, database,
client, or model-provider auto-instrumentation alongside this path; it would
duplicate spans and expand the capture boundary.

Use on-demand profiling only for a bounded local reproduction or approved
incident window. Select an already approved runtime profiler, limit capture
duration and access, keep payloads and secrets out of artifacts, then stop the
profiler and dispose of its output under the incident's retention rules. The
repository does not add a profiler dependency, endpoint, daemon, or continuous
capture subsystem.
