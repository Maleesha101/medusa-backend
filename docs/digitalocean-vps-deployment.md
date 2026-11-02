# DigitalOcean VPS deployment readiness

## Status and safety boundary

DigitalOcean is the selected hosting provider for MEDUSA's planned VPS deployment. No Droplet is assumed to exist yet, and this document does not provision infrastructure.

Selecting DigitalOcean does **not** prove that a Droplet exposes KVM, nested virtualization, a usable VM/microVM boundary, or the network controls required for hostile challenge code. Do not select or enable a sandbox runtime from provider branding or plan descriptions alone.

Keep `SANDBOX_PROVIDER=unavailable`. Do not expose participant-facing sandbox launch endpoints, place a Docker/container-runtime socket in a workload, or run challenge code on the API/control-plane host. The existing [Linux host preflight](sandbox-linux-host-preflight.md) is a later read-only evidence-gathering step, not a security certification.

## Intended topology

Start with a modular-monolith application deployment, but preserve a hard security boundary between application services and any future hostile-code execution:

- **Application/control plane:** MEDUSA FastAPI API, worker processes for trusted application jobs, PostgreSQL, Redis, and object-storage integration. These services hold application data and credentials and must never share a challenge-workload trust boundary.
- **Sandbox host:** a separate, dedicated DigitalOcean Droplet reserved for the future sandbox worker/runtime, only after the isolation design is approved. It must not host the public API, primary database, Redis, or unrelated workloads.
- **External dependencies:** use managed or separately isolated data services where practical. Object storage credentials should be narrowly scoped; challenge workloads must not receive them.
- **Administration:** operators connect through SSH keys and a restricted management path. Do not expose database, Redis, Docker, or administrative ports to the public internet.

This is a target architecture, not a claim that deployment automation or a sandbox provider currently exists. The application may be deployed separately from the future sandbox host; do not combine them merely to reduce initial cost.

## Before purchasing a Droplet

Complete these decisions first:

1. **Region:** choose a DigitalOcean region based on the expected majority of MEDUSA users and acceptable latency to required data services. Keep dependent services in a compatible/nearby region where possible. Do not choose a region solely because it is the default.
2. **Operating system:** plan for a supported Ubuntu LTS image (Ubuntu 24.04 LTS is a reasonable initial choice at the time this guide was written). Re-check DigitalOcean's currently offered images and Ubuntu support status when creating the Droplet.
3. **Sizing:** estimate API traffic, worker concurrency, database/cache memory, upload volume, log retention, and expected simultaneous challenges separately. Do not treat a small general-purpose Droplet as a safe sandbox host. For an initial application-only staging environment, size from measured resource use; production database and sandbox capacity should be planned independently.
4. **Virtualization requirement:** before buying a Droplet intended to host a VM/microVM runtime, obtain confirmation for the exact plan/region/image about KVM device access and virtualization support. If DigitalOcean cannot provide clear confirmation, purchase only a disposable test Droplet for evidence gathering; do not assume nested virtualization works.
5. **Budget:** include Droplet cost, backups/snapshots, monitoring, object storage, data transfer, managed database/cache if selected, and a recovery reserve. Confirm current prices in the DigitalOcean control panel before purchase; this guide intentionally does not pin prices.
6. **Ownership:** name the person responsible for OS updates, firewall changes, backup restore tests, monitoring alerts, and security incident response.

## Initial Droplet hardening checklist

After creating a test or production Droplet:

- [ ] Use a supported Ubuntu LTS image and apply security updates before deploying application code.
- [ ] Inject an operator-controlled SSH public key during provisioning. Keep the private key off the server and out of the repository.
- [ ] Create a named, least-privilege operator account; verify key-based access before changing SSH settings.
- [ ] Disable password-based SSH and direct root SSH login only after confirming the named account can administer the host. Keep a recovery path.
- [ ] Configure a DigitalOcean Cloud Firewall and host firewall with default-deny inbound policy.
- [ ] Permit SSH only from trusted administrator IP ranges where practical; expose only the required public application ports (normally 80/443 behind a reverse proxy).
- [ ] Do not expose PostgreSQL (5432), Redis (6379), Docker/container-runtime APIs, internal worker ports, or metrics/admin endpoints publicly.
- [ ] Prefer private networking for service-to-service traffic. Restrict database and cache access to the exact application/worker sources that need it.
- [ ] Configure unattended security updates or a documented patch cadence and reboot process.
- [ ] Enable encrypted backups/snapshots where supported, define retention, and test restoration. A snapshot is not a substitute for application-consistent database backups.
- [ ] Configure monitoring for CPU, memory, disk usage, disk I/O, network, service health, and backup failures; route alerts to an actively monitored destination.
- [ ] Centralize and rotate logs without recording access tokens, passwords, private keys, challenge flags, or full environment dumps.
- [ ] Document recovery access, incident contacts, and Droplet rebuild procedures.

Cloud Firewall rules and host firewall rules should agree. A Cloud Firewall is an important perimeter control, not a substitute for host-level policy or application authorization.

## Configuration and secret handling

The repository's `.env.example` contains local-development defaults. It is **not** a production configuration file. In particular, its database password and authentication signing key are development-only placeholders.

For each deployment:

- Create secrets outside Git, using a managed secret store or a root-readable deployment environment file with restrictive permissions (for example, mode `0600`).
- Generate a unique, high-entropy `AUTH_SECRET_KEY` for each environment. Never reuse the example value.
- Supply production PostgreSQL and Redis URLs through the deployment's secret mechanism. Do not bind database/cache listeners to public interfaces.
- Configure SMTP credentials and a production password-reset URL only when those features are deployed.
- Set `APP_ENV` to the environment's production value and select an appropriate log level; verify the application's accepted settings before deployment.
- Keep credentials out of shell history, command-line arguments, CI logs, issue comments, screenshots, and support bundles.
- Rotate credentials after suspected exposure and document which services require restart/redeployment.
- Do not pass application secrets, cloud API tokens, database credentials, or object-storage credentials into challenge workloads.

Do not commit a filled-in `.env`, private SSH key, DigitalOcean API token, database dump, or raw host inventory. Use placeholders in examples and redact secrets from diagnostic output.

## Post-provisioning evidence checklist

Complete this on the actual disposable/test Droplet before deciding on the sandbox runtime. Record only sanitized results and evidence references; do not paste secrets or full environment dumps into the repository.

### 1. Record host facts

- [ ] Record Droplet plan/size, region, image, kernel version, and architecture.
- [ ] Record whether DigitalOcean confirms KVM/direct or nested virtualization support for this exact plan.
- [ ] Run the read-only probe from the repository root:

  ```bash
  python -c "from app.services.sandbox_host_probe import probe_linux_host_capabilities; print(probe_linux_host_capabilities())"
  ```

- [ ] Interpret `null` as unknown and `false` as not observed. Neither can be counted as a passing control.
- [ ] Do not infer that KVM is usable merely because `/dev/kvm` exists; verify access from the intended least-privilege worker identity and confirm the virtualization behavior with a disposable test.

### 2. Verify enforcement from outside a workload

- [ ] Demonstrate a VM/microVM or other independently reviewed strong isolation boundary. A conventional container alone is not accepted as sufficient evidence for hostile challenge code.
- [ ] Demonstrate CPU, memory, process-count, storage, and wall-clock limits from the host/provider side.
- [ ] Demonstrate a hard provider/host-enforced deadline that still stops a workload if MEDUSA workers or the database become unavailable.
- [ ] Demonstrate bounded, disposable per-workload storage and cleanup after normal stop, timeout, partial launch, and host/worker restart.

### 3. Verify network isolation

- [ ] Establish default-deny workload egress at a boundary outside the workload.
- [ ] Test and block access to the host, control plane, DigitalOcean metadata service, database, Redis, administrative endpoints, and other tenants/workloads.
- [ ] Define whether challenges need outbound internet access. If required, document and enforce a narrow allowlist; otherwise deny it.
- [ ] Verify DNS behavior and prevent DNS from becoming an egress bypass.
- [ ] Keep public ingress to workload instances disabled unless an explicitly reviewed design requires a narrowly scoped path.

### 4. Review before enabling anything

- [ ] Use a dedicated least-privilege worker identity with no host root, runtime socket, application secrets, or cloud credentials exposed to challenge code.
- [ ] Test idempotent stop and reconciliation after API timeout, partial launch, worker termination, and database failure.
- [ ] Run hostile-workload tests in a disposable environment without production credentials.
- [ ] Obtain an independent security review and record the accepted residual risks.
- [ ] Update the sandbox deployment ADR and capability manifest with evidence references and an owner for every claim.

A passing host probe or operator manifest is not security certification. If any required control is unknown, missing, or unverified, keep sandbox execution disabled.

## Operational readiness before production traffic

- [ ] Confirm health/readiness checks and restart behavior for each deployed service.
- [ ] Test database backup and restore, migration/rollback procedure, and Redis recovery expectations.
- [ ] Load-test the API and workers at expected concurrency; establish CPU, memory, latency, and queue-depth alerts.
- [ ] Define log retention, access controls, incident response, and credential rotation.
- [ ] Document how to rebuild a Droplet from reviewed configuration without relying on a manually modified server.
- [ ] Review public endpoints, TLS termination, CORS, trusted proxy settings, and rate limits before opening traffic.

## Current project state

- Hosting target: DigitalOcean VPS selected; no Droplet provisioned yet.
- Application deployment automation: not established by this readiness guide.
- Sandbox isolation mechanism: not selected or approved.
- `SANDBOX_PROVIDER=unavailable` remains mandatory until host-specific evidence, enforcement tests, and security review are complete.

See [the sandbox deployment ADR](adr/sandbox-deployment-target.md) and [Linux sandbox host preflight](sandbox-linux-host-preflight.md) for the existing threat model and probe details.
