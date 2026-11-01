# Linux Sandbox Host Capability Preflight

## Purpose and safety boundary

This preflight is a readiness aid for the selected DigitalOcean dedicated Linux VPS target. Follow the [DigitalOcean VPS deployment readiness guide](digitalocean-vps-deployment.md) for pre-purchase planning and host hardening. It does **not** start containers or VMs, execute challenge code, change host configuration, or certify the host as secure. A capability being present does not prove that it is correctly configured or safely enforced.

Keep `SANDBOX_PROVIDER=unavailable`. Neither the host probe nor the manifest evaluator enables a provider. Unknown or inaccessible observations must not be interpreted as success.

## Read-only host probe

Run from the repository root:

```bash
python -c "from app.services.sandbox_host_probe import probe_linux_host_capabilities; print(probe_linux_host_capabilities())"
```

The probe uses read-only `/proc`, `/sys`, and device metadata observations. Its filesystem functions are injectable so tests do not require root, KVM, or a real VPS. It reports:

- `linux_host`: kernel OS type.
- `linux_namespaces_present`: presence of expected current-process namespace handles.
- `cgroups_v2_present`: whether the cgroup v2 controller file is readable and non-empty.
- `seccomp_kernel_support_observed`: whether the kernel advertises the seccomp `allow` action.
- `apparmor_or_selinux_active`: whether the AppArmor enabled flag or SELinux enforcing flag indicates active MAC.
- `kvm_device_present` and `kvm_device_accessible_to_probe`: separate observations; device presence does not imply worker access.

A value of `null` means the probe could not establish the fact. A false value means the checked condition was not observed. These are observations, not an activation decision. Namespace handles describe the probe process; cgroup controller availability does not prove per-workload limits; seccomp action availability does not prove the intended workload profile is applied.

## Required operator verification

Record evidence and an owner for each claim before marking it verified in the existing capability manifest:

1. **Isolation boundary:** document whether the VPS supports KVM and a VM/microVM design, or another independently reviewed isolation mechanism. A conventional container alone is not accepted as proof against hostile workloads.
2. **Resource enforcement:** verify CPU, memory, process, storage, and wall-clock limits from outside the workload. Confirm that the provider enforces a hard deadline even if MEDUSA workers stop.
3. **Network egress:** verify default-deny policy at the host/network boundary. Test attempts to reach the host, control plane, cloud metadata addresses, database, Redis, administrative services, DNS, and other sandboxes. Document any explicit challenge egress allowlist.
4. **Storage:** ensure writable storage is bounded, isolated per workload, and disposable.
5. **Least privilege:** use a dedicated worker identity. No runtime socket, host root, application secrets, or cloud credentials may be mounted into workloads.
6. **Lifecycle:** test idempotent stop and reconciliation after partial launch, API timeout, worker termination, and database failure.
7. **Host operations:** record distribution/kernel patching, firewall ownership, monitoring, backups, incident response, and security-update responsibility.
8. **Security review:** run hostile-workload tests in a disposable environment and obtain independent review before any provider is enabled.

Do not place secrets, credentials, raw environment dumps, or sensitive host inventory in a capability report. Keep evidence in approved operations documentation.

## Operator manifest evaluator

The existing manifest CLI evaluates only operator-supplied claims; it does not inspect or change the host:

```bash
python -m app.services.sandbox_host_preflight_cli docs/examples/sandbox-host-capabilities.example.json
```

A version 1 manifest contains exactly `schema_version` and `capabilities`. Values are `true`, `false`, or `null`; the example deliberately marks every capability unknown. Missing, false, or null required controls block readiness. Unknown identifiers and malformed manifests are rejected safely.

The CLI prints deterministic JSON with `ready`, `blocked`, `missing`, and `unknown`. Exit code `0` means all required operator claims were explicitly marked true, `1` means readiness is blocked, and `2` means the manifest is invalid. A ready manifest is not security certification.

## Current status

- Deployment provider/target: DigitalOcean dedicated Linux VPS selected; no Droplet provisioned yet.
- Concrete isolation mechanism/provider: pending VPS capability evidence and threat-model review.
- Host probe: read-only observations only; it does not certify or enable a provider.
- Provider activation: blocked; `SANDBOX_PROVIDER=unavailable` remains mandatory.
