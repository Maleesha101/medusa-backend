# Sandbox Lifecycle Service

## Scope

This increment adds database-backed lifecycle policy only. It does not launch or stop a runtime, add participant-facing HTTP endpoints, or make the unavailable provider executable. Keep the provider fail-closed until an isolated runtime implementation has been reviewed.

## Request policy

A sandbox request is accepted only for a published challenge in a public, active competition. The requested expiry must be timezone-aware, in the future, and no more than two hours from the request time. Defaults allow at most two active (pending/running, unexpired) instances per owner and twenty per competition. These are conservative initial policy defaults, not yet environment-configurable.

The service creates a `pending` metadata record and records a `sandbox.requested` audit event in the same transaction. Runtime launch is deliberately a separate trusted operation.

## Allowed transitions

- `pending -> running | stopped | failed | expired`
- `running -> stopped | failed | expired`
- `stopped`, `failed`, and `expired` are terminal states.

A transition requires the owner or an admin. Missing and unauthorized instances produce the same not-found error. Starting requires an unexpired instance and an opaque provider ID supplied by trusted internal code. Failure metadata is restricted to a short code; exception messages, credentials, and arbitrary request data must never be recorded. Each transition writes an audit event with prior and new state.

## Operational limitations

The current quota check is an application-level count and does not yet provide a database-backed reservation lock for concurrent requests. Before exposing a public create endpoint or enabling real provider launches, add concurrency-safe quota reservation, settings-based quotas, an expiry worker/reconciliation strategy, and provider cleanup semantics. The API must not allow clients to submit provider IDs or directly choose lifecycle states.
