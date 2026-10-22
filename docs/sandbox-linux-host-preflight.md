# Linux Sandbox Host Capability Preflight

## Purpose and safety boundary

This preflight is a deterministic readiness gate for a future VPS or dedicated
Linux-host provider. It evaluates a mapping of operator-verified capability
claims; it does **not** probe the machine, start containers, execute challenge
code, or certify the host as secure. A report marked ready is necessary but not
sufficient for provider approval.

Keep `SANDBOX_PROVIDER=unavailable`. This preflight does not register or enable
a provider. Missing, false, or unverified controls must block any future
activation.

## Required capability identifiers

The evaluator in `app/services/sandbox_host_preflight.py` requires every item
below to be explicitly verified:

- `linux_namespaces`: required namespaces are available and correctly scoped.
- `cgroups_v2` and `cpu_memory_pid_limits`: resource limits are enforced by
  the host, not just checked by the API.
- `strong_workload_isolation`: the selected boundary is justified for hostile
  code (for example, an independently reviewed VM/microVM or sandboxed runtime
  design); ordinary containers alone do not prove adequate isolation.
- `seccomp` and `apparmor_or_selinux`: restrictive syscall and mandatory
  access-control policies are enforced.
- `network_namespaces`, `host_firewall_default_deny`, and
  `block_metadata_and_internal_egress`: workload traffic is isolated and
  default-denied, including host, control plane, metadata, database, Redis,
  administrative services, and other sandboxes.
- `bounded_ephemeral_storage`: writable storage is bounded and disposable.
- `provider_enforced_hard_deadline`: a trusted provider stops workloads even
  if the application scheduler is down.
- `idempotent_cleanup_and_reconciliation`: partial launches, worker restarts,
  and orphaned instances can be reconciled safely.
- `immutable_image_allowlist`: only server-selected, immutable image digests
  can run.
- `dedicated_least_privilege_worker_identity`: host access is restricted to a
  dedicated service identity.
- `no_runtime_socket_or_host_secret_mounts`: workload configuration never
  exposes the container-runtime socket, host root, application secrets, or
  cloud credentials.

## Operator verification checklist

Record evidence and an owner for each claim before marking it true:

1. Confirm the supported Linux distribution, kernel, patch level, and access to
   maintain security updates.
2. Verify namespace, cgroup v2, syscall-filter, and AppArmor/SELinux support on
   the exact host image.
3. Document the isolation mechanism and threat model; do not treat a rootless
   container or Docker alone as proof against hostile workloads.
4. Verify CPU, memory, process, storage, and wall-clock limits from outside the
   workload.
5. Verify network policy with tests that attempt host, internal service,
   metadata, DNS, and outbound access; default deny must be enforced at the
   host/network boundary.
6. Confirm the worker identity has only the permissions it needs and that no
   runtime socket or secrets are mounted into workload filesystems.
7. Test hard-stop behavior and cleanup after API timeout, worker termination,
   database failure, and partial launch.
8. Run hostile-workload tests in a disposable isolated environment, then obtain
   independent security review and operational sign-off.

Do not place secrets, credentials, raw environment dumps, or sensitive host
inventory in the capability report. Keep evidence in the approved operations
documentation system.

## Implementation note

`evaluate_sandbox_host_capabilities` is a pure evaluator for a trusted,
operator-verified mapping. It intentionally does not infer support from OS
names or accept missing/unknown controls as warnings. Future probing must be
implemented separately, use least privilege, avoid executing untrusted code,
and be reviewed before its output can be treated as evidence.

## Current status

- Concrete provider: unavailable.
- Host capability detection: not implemented; capability claims must not be
  fabricated or automatically marked true.
- Provider activation: blocked pending host-specific evidence, integration
  tests, hostile-workload tests, and security sign-off.


## Operator CLI

The manifest CLI evaluates only the capability claims supplied by an operator. It does not inspect or change the host and does not enable a provider.

Run it from the repository root:

```bash
python -m app.services.sandbox_host_preflight_cli /path/to/capabilities.json
```

The JSON file must be an object whose keys are the known capability identifiers above and whose values are `true`, `false`, or `null`. Omitted required identifiers are reported as unknown. Unknown identifiers and invalid value types are rejected without echoing manifest contents.

The command prints deterministic JSON with `ready`, `blocked`, `missing`, and `unknown` fields. Exit code `0` means all required claims were explicitly marked true; exit code `1` means readiness is blocked; exit code `2` means the manifest could not be validated. A ready report is not security certification. Never mark a capability true without recorded evidence and review. Keep `SANDBOX_PROVIDER=unavailable`.
