# Sandbox Provider Readiness Checklist

## Status

The sandbox controller is currently an interface with an unavailable, fail-closed implementation. This checklist is the release gate for adding a concrete execution provider. Completing this document does not enable sandbox launches and is not a production-readiness certification.

**Do not configure a real provider or expose participant-facing sandbox endpoints until every required control below has an implementation, a test, and an owner.**

## 1. Provider boundary and trust

- [ ] Keep provider calls outside the FastAPI request process where practical; use a dedicated worker/service identity.
- [ ] Accept only server-selected, allowlisted challenge images pinned by immutable digest. Never accept an arbitrary image reference from a participant.
- [ ] Generate and persist provider instance IDs only from trusted provider responses. Never accept provider IDs or lifecycle state from clients.
- [ ] Define idempotent launch/stop behavior, bounded timeouts, and safe handling of provider API errors.
- [ ] Ensure a lost response or worker restart can reconcile provider workloads with database records without creating duplicate workloads.
- [ ] Keep the unavailable controller as the default. Provider selection must be explicit, validated at startup, and reversible with a deployment kill switch.

## 2. Workload isolation

- [ ] Run workloads as an unprivileged identity with no host PID, IPC, or network namespaces.
- [ ] Never mount the host container-runtime socket, host root, cloud credentials, or application secrets into a challenge workload.
- [ ] Apply CPU, memory, process-count, storage, file-descriptor, and execution-time limits on the provider side, not only in application validation.
- [ ] Use a read-only root filesystem where possible and a bounded ephemeral writable filesystem.
- [ ] Apply a restrictive seccomp profile and mandatory access controls (for example, AppArmor or SELinux) supported by the deployment platform.
- [ ] Ensure workloads cannot access the host, control plane, cloud metadata endpoints, database, Redis, internal admin services, or other tenants.
- [ ] Deny outbound network access by default. Add explicit, reviewed exceptions only when a challenge requires them.
- [ ] Separate workloads by tenant/sandbox and verify that stopping or deleting one workload cannot affect another.

## 3. Lifecycle, quotas, and cleanup

- [ ] Enforce maximum lifetime, owner/competition quotas, and resource budgets at the trusted service boundary.
- [ ] Set provider-side hard deadlines so a missed scheduler run cannot leave a workload running indefinitely.
- [ ] Make stop/delete operations idempotent and retryable; distinguish “already absent” from a genuine cleanup failure.
- [ ] Reconcile expired database records and orphaned provider workloads on a bounded schedule.
- [ ] Bound retries with exponential backoff and jitter, and alert on persistent failures, old pending records, and provider/database drift.
- [ ] Define behavior for partial launch failures, database commit failures, worker termination, and provider outages.
- [ ] Ensure cleanup never logs provider credentials, raw exception messages, challenge secrets, or environment contents.

## 4. Observability and incident response

- [ ] Export durable counters and latency/error measurements to the deployment monitoring system; current in-process counters reset on restart.
- [ ] Include a correlation ID and sandbox ID in structured events without exposing secrets or participant payloads.
- [ ] Alert on launch/cleanup failure rate, cleanup backlog age, expired-but-running workloads, quota rejections, and provider API saturation.
- [ ] Document operator procedures to disable launches, stop all workloads, rotate provider credentials, and investigate suspected isolation escape.
- [ ] Define retention and access control for provider logs and sandbox metadata.

## 5. Verification before enabling a provider

- [ ] Unit-test allowlist enforcement, input validation, timeout handling, retry classification, idempotency, and safe error mapping.
- [ ] Integration-test launch, stop, expiry, retry, restart recovery, and orphan reconciliation against a disposable provider environment.
- [ ] Test hostile workloads: resource exhaustion, process spawning, filesystem escape attempts, DNS/egress attempts, metadata-service access, and cross-tenant access.
- [ ] Verify that CI can run tests without privileged runtime access or production credentials.
- [ ] Run migration, full test, lint, and formatting checks, plus dependency and image vulnerability scans.
- [ ] Complete a threat-model review and obtain an explicit operational/security sign-off before enabling the provider in staging.
- [ ] Perform a staged rollout with a small allowlisted challenge set, operational alerts, and a tested rollback/kill switch before broader availability.

## 6. Required implementation sequence

1. Select the deployment target and document its isolation primitives and limitations.
2. Implement a provider adapter behind the existing `SandboxController` protocol; retain the unavailable adapter as the default.
3. Add provider-specific configuration with safe startup validation and no implicit activation.
4. Implement reconciliation for partial launches and orphaned workloads.
5. Add provider integration and hostile-workload tests in an isolated environment.
6. Complete the security review and operational runbook.
7. Enable the provider only through an explicit deployment change after sign-off.

## Related implementation

- `app/services/sandbox_controller.py` — trusted provider protocol and fail-closed default.
- `app/services/sandbox_lifecycle.py` — request policy, quotas, and state transitions.
- `app/services/sandbox_expiry_worker.py` — bounded expiry reconciliation.
- `app/services/sandbox_cleanup_worker.py` — bounded provider cleanup retries.
- `docs/sandbox-lifecycle-service.md` — current lifecycle and cleanup behavior.
- `docs/security-baseline.md` — platform security baseline.

This checklist is intentionally provider-neutral. The concrete design cannot be finalized until the deployment target and its supported isolation controls are selected.
