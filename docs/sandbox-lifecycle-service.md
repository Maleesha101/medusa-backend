# Sandbox Lifecycle Service

## Scope

This increment adds database-backed lifecycle policy only. It does not launch or stop a runtime, add participant-facing HTTP endpoints, or make the unavailable provider executable. Keep the provider fail-closed until an isolated runtime implementation has been reviewed.

## Request policy

A sandbox request is accepted only for a published challenge in a public, active competition. The requested expiry must be timezone-aware, in the future, and no more than two hours from the request time. Defaults allow at most two active (pending/running, unexpired) instances per owner and twenty per competition, with a maximum lifetime of two hours. Deployments can override these values with `SANDBOX_MAX_ACTIVE_PER_OWNER`, `SANDBOX_MAX_ACTIVE_PER_COMPETITION`, and `SANDBOX_MAX_LIFETIME_MINUTES`. Values are validated at startup: owner limit 1–100, competition limit 1–10000, and lifetime 5–720 minutes. Explicit `SandboxPolicy` values may still be supplied by trusted internal callers and tests.

Before counting active records, the service locks the owner and competition rows in a fixed order. On PostgreSQL, this serializes quota checks for concurrent requests that share an owner or competition, preventing both requests from observing the same available slot. SQLite ignores `FOR UPDATE`, so its test database does not validate this concurrency guarantee. All sandbox creation paths must use this service; bypassing it bypasses the quota protection.

The service creates a `pending` metadata record and records a `sandbox.requested` audit event in the same transaction. Runtime launch is deliberately a separate trusted operation.

## Allowed transitions

- `pending -> running | stopped | failed | expired`
- `running -> stopped | failed | expired`
- `stopped`, `failed`, and `expired` are terminal states.

A transition requires the owner or an admin. Missing and unauthorized instances produce the same not-found error. Starting requires an unexpired instance and an opaque provider ID supplied by trusted internal code. Failure metadata is restricted to a short code; exception messages, credentials, and arbitrary request data must never be recorded. Each transition writes an audit event with prior and new state.

## Operational limitations

The `expire_due_sandboxes` service marks overdue pending/running records as expired in bounded batches, sets the stop timestamp, and records an audit event. A scheduled worker still needs to invoke this function regularly. The one-shot command `python -m app.services.sandbox_expiry_worker --batch-size 100` runs one bounded reconciliation batch and is intended to be called periodically by the deployment scheduler. Configure the cadence and alerting in deployment infrastructure; this repository does not install a scheduler automatically. PostgreSQL workers use `SKIP LOCKED` to avoid processing the same rows concurrently. This metadata reconciliation does not stop a runtime; provider cleanup uses persisted `cleanup_status`, `cleanup_attempts`, and a safe error code. Terminal transitions with a provider ID queue cleanup. `python -m app.services.sandbox_cleanup_worker --batch-size 50` retries a bounded batch; successful stops are marked cleaned, and failures remain eligible for a later retry after bounded exponential backoff (30 seconds by default, capped at one hour). `cleanup_next_attempt_at` prevents a failing provider from being hammered on every scheduler run. The default controller is unavailable and fails closed, so the worker will report failures until deployment code explicitly wires a reviewed provider. Configure scheduler cadence and alerting outside this repository. Do not enable real provider launches until a concrete isolated provider, retry/backoff policy, and cleanup behavior have been reviewed. The API must not allow clients to submit provider IDs or directly choose lifecycle states.


## Cleanup observability

The cleanup reconciliation service emits structured log events for individual successes/failures and batch totals. Events include sandbox ID, attempt count, cleanup status, safe error code, and retry timestamp; provider exception messages and credentials are not logged. The worker also records counters through `sandbox_cleanup_metrics` for batches, processed instances, successful cleanups, and failures. These counters are in-process only and reset on process restart; they are a hook for deployment-specific metrics export, not a durable monitoring backend. Configure scheduler alerts on non-zero worker exits and repeated cleanup failures, and export the structured logs/counters to the deployment's monitoring platform.
