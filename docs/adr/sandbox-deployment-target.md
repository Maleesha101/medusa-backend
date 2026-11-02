# ADR: Sandbox Deployment Target and Isolation Model

- Status: **Selected target — isolation design and provider approval pending evidence**
- Decision issue: [#31](https://github.com/Maleesha101/medusa-backend/issues/31)
- VPS readiness work: [#85](https://github.com/Maleesha101/medusa-backend/issues/85)
- DigitalOcean deployment planning: [#87](https://github.com/Maleesha101/medusa-backend/issues/87)
- [DigitalOcean VPS deployment readiness guide](../digitalocean-vps-deployment.md)

## Context

MEDUSA exposes a provider-neutral `SandboxController` protocol and defaults to `UnavailableSandboxController`. The `SANDBOX_PROVIDER` setting accepts only `unavailable`. Challenge code must be treated as hostile: a successful escape could compromise other participants, service credentials, or the control plane.

## Decision

The project owner selected **DigitalOcean** as the hosting provider and a **dedicated Linux VPS** as the intended deployment target for sandbox infrastructure.

This selects the hosting environment, not the isolation mechanism. It does not establish that the VPS provider exposes KVM, that a VM/microVM boundary is available, or that the host/network configuration meets the threat model. The concrete runtime remains unselected and unapproved until host-specific evidence and security review are complete.

## Required controls and evidence

A target must demonstrate, with platform configuration and tests:

- Strong isolation appropriate for hostile code. A conventional container alone is not accepted as proof of sufficient isolation. Evaluate hardware virtualization/KVM and a VM or microVM boundary where available; any alternative requires an explicit threat-model review.
- No privileged runtime socket, host filesystem, application secrets, or cloud credentials inside workloads.
- Default-deny egress, including host, control-plane, cloud metadata, database, Redis, and cross-tenant destinations.
- Provider-enforced CPU, memory, process, storage, and wall-clock limits.
- A hard provider-side deadline, idempotent stop, and reconciliation after partial launch or worker/database failure.
- Least-privilege workload identity, auditable operations, security updates, and incident response.
- Repeatable integration and hostile-workload tests without production credentials.

## VPS readiness work

Issue #85 adds a read-only, sanitized host-capability probe. Detection of a kernel feature or device is only an observation; it does not prove correct configuration or secure isolation. Network egress policy, metadata blocking, workload resource enforcement, hard deadlines, cleanup, and hostile-workload resistance require separate configuration evidence and tests.

The probe must not execute privileged commands, change host configuration, launch workloads, or expose sensitive host details. Unknown or inaccessible observations remain unknown and block readiness where required.

## Outstanding deployment facts

Before accepting a concrete isolation design, record:

1. DigitalOcean Droplet plan/size, region, virtualization type, kernel/distribution, and whether nested or direct KVM access is available for that exact plan.
2. Expected concurrent sandboxes and approximate per-sandbox CPU, memory, storage, and runtime.
3. Whether challenges need outbound network access, and if so, the explicit allowlist.
4. Budget, patching/backup arrangements, and the person responsible for security incidents.

## Deployment preparation

Issue #87 adds a DigitalOcean-specific pre-purchase and post-provisioning checklist. No Droplet is provisioned by that documentation. Region, Droplet size, KVM/virtualization access, and network enforcement must be verified against the actual selected Droplet; provider selection alone is not evidence that the sandbox threat model can be met.

## Consequences

- Keep `SANDBOX_PROVIDER=unavailable`; no concrete provider is approved.
- Do not add participant-facing launch endpoints or credentials as part of host preflight.
- Do not use or mount a Docker/container-runtime socket into challenge workloads.
- A successful preflight is not security certification or permission to enable execution.
- Provider implementation follows only after the VPS capabilities, isolation mechanism, network policy, resource enforcement, cleanup, and hostile-workload tests are reviewed.
