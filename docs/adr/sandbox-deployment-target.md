# ADR: Sandbox Deployment Target and Isolation Model

- Status: **Proposed — deployment owner decision required**
- Issue: [#31](https://github.com/Maleesha101/medusa-backend/issues/31)
- Scope: choose the execution boundary for untrusted CTF challenge workloads before implementing a concrete provider.

## Context

MEDUSA currently exposes a provider-neutral `SandboxController` protocol and defaults to `UnavailableSandboxController`. The `SANDBOX_PROVIDER` setting accepts only `unavailable`. Challenge code must be treated as hostile: a successful escape could compromise other participants, service credentials, or the control plane.

The repository does not establish the production hosting platform, expected concurrency, budget, operational staffing, or required challenge network access. Therefore this ADR compares options but does not pretend a final deployment target has been selected.

## Decision criteria

A target must demonstrate, with platform configuration and tests:

- Strong isolation appropriate for hostile code; containers alone are not automatically a sufficient security boundary.
- No privileged runtime socket, host filesystem, application secrets, or cloud credentials inside workloads.
- Default-deny egress, including host, control-plane, cloud metadata, database, Redis, and cross-tenant destinations.
- Provider-enforced CPU, memory, process, storage, and wall-clock limits.
- A hard provider-side deadline, idempotent stop, and reconciliation after partial launch or worker/database failure.
- Least-privilege workload identity, auditable operations, security updates, and incident response.
- Repeatable integration and hostile-workload tests without production credentials.

## Options

| Option | Advantages | Risks / costs | Evidence required |
|---|---|---|---|
| Managed Kubernetes with dedicated, hardened worker nodes | Mature scheduling, quotas, and operational ecosystem | Cluster misconfiguration can expose the control plane; ordinary pods may not provide enough isolation for hostile workloads; requires specialist operations | Node isolation strategy, runtime class/sandboxing mechanism, admission policy, NetworkPolicy enforcement, metadata protection, quota and deadline tests |
| Dedicated container hosts with a hardened runtime | Direct control over kernel, runtime, and networking; potentially simpler initial footprint | Host escape has a large blast radius; patching, scheduling, cleanup, and tenant separation become our responsibility | Host hardening, rootless/isolated runtime design, syscall/mandatory-access-control policy, per-workload network namespace, host firewall, automated patching and recovery tests |
| Hosted isolated-execution provider | May reduce infrastructure operations and provide purpose-built isolation | Vendor lock-in, cost and quota constraints, data handling concerns, dependency on provider semantics and availability | Independent security documentation, isolation guarantees, egress controls, resource enforcement, deletion semantics, regional/data policy, SLA, API idempotency and failure tests |

No option is approved solely by this comparison. A managed platform must be evaluated by its actual configuration and isolation guarantees, not its product label.

## Required owner input

Before changing this ADR to Accepted, confirm:

1. Where MEDUSA will be deployed and which infrastructure the team can operate.
2. Expected concurrent sandboxes and approximate per-sandbox CPU, memory, storage, and runtime.
3. Whether challenges need outbound network access, and if so, which destinations.
4. Budget and operational constraints, including who will respond to isolation incidents.

## Provisional direction

Do not implement or enable a concrete provider until the owner confirms the deployment context and the chosen option demonstrates the criteria above. Keep `SANDBOX_PROVIDER=unavailable` and retain the fail-closed controller. The next implementation issue should name the chosen platform and list its tested isolation controls.

## Consequences

- This ADR does not launch workloads, add runtime dependencies, expose endpoints, or add credentials.
- The final decision remains open pending deployment-owner input.
- Provider-specific implementation and hostile-workload integration tests remain follow-up work.
