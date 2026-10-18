# Sandbox Controller: Initial Contract

## Scope of this increment

This increment adds persistence for sandbox lifecycle metadata and defines a provider interface. It does **not** launch containers, execute challenge code, or expose sandbox management endpoints. The default controller intentionally raises `SandboxProviderUnavailable` so the application cannot accidentally start untrusted workloads.

## Lifecycle vocabulary

Persisted state values are:

- `pending` — a request has been accepted by a future orchestration layer but has not started.
- `running` — the trusted provider confirmed that the runtime started.
- `stopped` — the runtime was intentionally stopped.
- `failed` — provider launch or runtime failed.
- `expired` — the allowed lifetime elapsed and cleanup was requested or confirmed.

A later API/service increment must define and test allowed transitions, idempotent stop/cleanup, expiry handling, and reconciliation when provider state disagrees with the database. Do not expose state mutation as a client-controlled field.

## Persistence

The `sandbox_instances` table associates a challenge and owner account with state, expiry, lifecycle timestamps, and an opaque provider instance ID. Provider IDs are assigned only by the trusted provider. They are not API request fields and must not be accepted from participants.

## Provider contract

`app.services.sandbox_controller.SandboxController` is the boundary for launch and stop operations. A concrete implementation must be supplied through trusted configuration and must fail closed when unavailable. The API process must not expose a host Docker socket or provide participants arbitrary container-runtime controls.

Before enabling a real provider, require at least:

- immutable, trusted image references and an allowlist;
- CPU, memory, process-count, disk, and wall-clock limits;
- network isolation, default-deny egress, and no access to host/metadata services;
- no host mounts or Docker socket;
- scoped provider credentials and a separate execution boundary;
- bounded concurrent instances per user, team, and competition;
- reliable cleanup after expiry, cancellation, provider failure, and API restart;
- authorization tests proving users cannot inspect or stop another user's instance;
- audit events for privileged lifecycle operations.

## Validation for this increment

The controller's default implementation is covered by tests that confirm launch and stop fail closed when no safe provider is configured. The next increment should add service/API behavior only after lifecycle transitions, concurrency quotas, ownership policy, and cleanup semantics are agreed and tested.
